import numpy as np
import time
from bs4 import BeautifulSoup
from selenium import webdriver
from skaero.atmosphere import coesa
import geopy.distance
import json
import pandas as pd


class Flight:
    def __init__(self, data=None, name=None, date=None, dest=None, origin=None, url=None):
        self.data = data
        self.name = name
        self.date = date
        self.dest = dest
        self.origin = origin
        self.url = url

    def clean_data(self):
        # Clean zero time
        self.data = np.delete(self.data, np.argwhere(self.delta_t[1:] == 0) + 1, 0)
        # Clean massive variations
        rol = pd.DataFrame(self.data).rolling(10, center=True)
        to_delete = np.unique(
            np.argwhere(
                np.nan_to_num(
                    np.abs(self.data[5:-4] - rol.mean()[5:-4]) / rol.std()[5:-4]
                    ) > 1.96)
            [:, 0])
        self.data = np.delete(self.data, to_delete, 1)

    def save(self, filename=None):
        if filename is None:
            name = self.name
            date = "-".join([str(x) for x in self.date])
            filename = f"{name} {date}.json"
        with open(filename, 'w') as out_file:
            info_dict = {
                "name": self.name,
                "date": self.date,
                "origin": self.origin,
                "dest": self.dest,
                "url": self.url,
                "data": self.data.tolist()
            }
            json.dump(info_dict, out_file)

    @staticmethod
    def open_file(filename):
        with open(filename, 'r') as in_file:
            info_dict = json.load(in_file)
            return Flight(
                data=np.array(info_dict["data"]),
                name=info_dict["name"],
                date=info_dict["date"],
                origin=info_dict["origin"],
                dest=info_dict["dest"],
                url=info_dict["url"]
            )

    @property
    def altitude(self):
        return self.data[:, 6] * 0.4038

    @property
    def delta_altitude(self):
        delta_alt = self.altitude - np.roll(self.altitude, 1)
        delta_alt[0] = 0
        return delta_alt

    @property
    def delta_distance(self):
        d = np.zeros(shape=self.data.shape[0])
        for idx in range(1, self.data.shape[0]):
            d[idx] = geopy.distance.geodesic(self.data[idx - 1, 1:3], self.data[idx, 1:3]).meters
        return np.sqrt(np.square(self.delta_altitude) + np.square(d))

    @property
    def delta_t(self):
        delta_t = self.data[:, 0] - np.roll(self.data[:, 0], 1)
        delta_t[0] = 0
        return delta_t

    @property
    def _delta_t_non_singular(self):
        delta_t_non_singular = self.delta_t
        delta_t_non_singular[0] = 1
        return delta_t_non_singular

    @property
    def delta_v(self):
        delta_v = self.velocity - np.roll(self.velocity, 1)
        delta_v[0] = 0
        return delta_v

    @property
    def velocity(self):
        return self.data[:, 4] * 0.51444 / 2 + self.data[:, 5] * 0.44704 / 2

    @property
    def time_step(self):
        return self.data[:, 0] - self.data[0, 0]

    @property
    def acceleration(self):
        return self.delta_v / self._delta_t_non_singular

    @property
    def q_infinity(self):
        _, _, _, rho = coesa.table(self.altitude)
        return 0.5 * rho * self.velocity ** 2

    def drag(self, area, cd):
        return self.q_infinity * area * cd

    def drag_work(self, area, cd):
        return self.drag(area, cd) * self.delta_distance

    def drag_work_rate(self, area, cd):
        return self.drag_work(area, cd) / self._delta_t_non_singular

    def potential_work(self, mass):
        g = 9.81
        return g * mass * self.delta_altitude

    def potential_work_rate(self, mass):
        return self.potential_work(mass) / self._delta_t_non_singular

    def kinetic_work(self, mass):
        delta_k = np.square(self.velocity) - np.square(np.roll(self.velocity, 1))
        delta_k[0] = 0
        return 0.5 * mass * delta_k

    def kinetic_work_rate(self, mass):
        return self.kinetic_work(mass) / self._delta_t_non_singular

    def work_addition(self, mass, area, cd, recovery_percentage=0):
        work_required = self.potential_work(mass) + \
                        self.kinetic_work(mass) + \
                        self.drag_work(area, cd)
        work_required[work_required < 0] *= recovery_percentage
        return work_required

    def work_rate_addition(self, mass, area, cd, recovery_percentage=0):
        return self.work_addition(mass, area, cd, recovery_percentage=recovery_percentage) \
               / self._delta_t_non_singular


class FlightAwareRecorder:
    def __init__(self):
        self.driver = webdriver.Chrome()

    def get_valid_flights(self, in_url="https://flightaware.com/live/aircrafttype/B763"):
        self.driver.get(in_url)
        trs = BeautifulSoup(self.driver.page_source, features="html5lib") \
            .find("table", {"class": "prettyTable"}) \
            .find("tbody") \
            .find_all("tr")
        urls = []
        for item in trs:
            ft = list(item.strings)[-1]
            ft_num = 60 * int(ft[0:2]) + int(ft[3:5])
            if 360 > ft_num > 120:
                urls.append(f"https://flightaware.com{item.find('a').attrs['href']}")
        return urls

    def get_historical_flights(self, base_url):
        self.driver.get(base_url)
        historical = BeautifulSoup(self.driver.page_source, features="html5lib") \
            .find("div", {"class": "flightPageDataTableContainer"}) \
            .find_all("div", {"class": "flightPageDataTable"})[-1] \
            .find_all("div", {"class": "flightPageDataRowTall"})
        return [f"https://flightaware.com{h.attrs['data-target']}/tracklog" for h in historical]

    @staticmethod
    def _parse_row_bs(row_data):
        ds = [r.text if len(list(r.children)) == 1 else list(r.children)[0].text for r in row_data]
        q_time = time.mktime(time.strptime(ds[0] + " 2019", "%a %I:%M:%S %p %Y"))
        q_lat = float(ds[1])
        q_lon = float(ds[2])
        q_head = float(ds[3][2:-1])
        q_kts = float(ds[4])
        q_mph = float(ds[5])
        q_ft = float(ds[6].replace(',', ''))
        return [q_time, q_lat, q_lon, q_head, q_kts, q_mph, q_ft]

    def get_data(self, urls):
        if isinstance(urls, list):
            for url in urls:
                self.driver.get(url)
                self._get_url().save()
        else:
            self.driver.get(urls)
            self._get_url().save()

    def _get_url(self):
        info = [x.strip() for x in self.driver.title.split('✈')]
        trs = BeautifulSoup(self.driver.page_source, features="html5lib") \
            .find("table", {"class": "prettyTable"}) \
            .find("tbody") \
            .find_all("tr")
        data = [r for r in trs if not any(['flight_event' in cl for cl in r.attrs['class']])]
        data_arr = []
        for row in data:
            try:
                data_arr.append(self._parse_row_bs(row.find_all('td')))
            except ValueError:
                pass
            except IndexError:
                pass
        return Flight(
            data=np.array(data_arr),
            name=info[1],
            date=time.strptime(info[2], '%d-%b-%Y'),
            origin=info[3].split('-')[0].strip(),
            dest=info[3].split('-')[1].strip(),
            url=self.driver.current_url
        )
