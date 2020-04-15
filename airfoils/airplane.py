import numpy as np
from math import pi
import os

global_path = r"C:\Users\njsto\OneDrive\Documents\CodeProjects\electricAirplane\airfoils"


class Wing:
    def __init__(self, span, c0, r, theta1, theta2, theta3, resolution=1000):
        self.L = span
        self.c0 = c0
        self.R = r
        self.theta1 = theta1
        self.theta2 = theta2
        self.theta3 = theta3
        self.resolution = resolution

        self.x_coords = np.linspace(0, self.L, self.resolution)
        self._arg_r = np.argmax(self.x_coords > self.R)

        self.upr = -1 * np.tan(theta1 * pi / 180) * self.x_coords
        self.lwr = np.zeros(np.size(self.upr))
        self.lwr[:self._arg_r] = -np.tan(theta3 * pi / 180) * self.x_coords[:self._arg_r] - self.c0
        self.lwr[self._arg_r:] = -np.tan(theta3 * pi / 180) * self.R - np.tan(theta2 * pi / 180) * (
                self.x_coords[self._arg_r:] - self.R) - self.c0

        self.S = np.trapz(self.upr - self.lwr, self.x_coords)
        self.AR = self.L ** 2 / self.S

    def bending_deflection(self, weight_l, lift_l, engine_shear, t_c_l, h_c_l, b_c_l, youngs_modulus, initial_angle):
        weight_dist = weight_l(self)
        lift_dist = lift_l(self)
        t_c_dist = t_c_l(self)
        h_c_dist = h_c_l(self)
        b_c_dist = b_c_l(self)

        i_yy = b_c_dist * h_c_dist ** 3 / 12 - (b_c_dist - t_c_dist) * (h_c_dist - t_c_dist) ** 3 / 12

        derivatives = np.zeros((5, self.resolution))
        derivatives[4, :] = (weight_dist + lift_dist) / 2
        derivatives[3, :] = np.cumsum(derivatives[4]) * self.L / self.resolution
        derivatives[3, :] -= derivatives[3, -1] + engine_shear(self)
        derivatives[2, :] = np.cumsum(derivatives[3]) * self.L / self.resolution
        derivatives[2, :] -= derivatives[2, -1]
        derivatives[1, :] = np.cumsum(derivatives[2] / (youngs_modulus * i_yy)) * self.L / self.resolution
        derivatives[1, :] -= derivatives[1, 0] + initial_angle * pi / 180
        derivatives[0, :] = np.cumsum(derivatives[1]) * self.L / self.resolution
        derivatives[0, :] -= derivatives[0, 0]

        return i_yy, derivatives

    def save_files(self, airfoil, offset, bending_deflection, thickness_percent, twist_degs,
                   path=global_path, run_sw=False):
        sw = SolidWorks() if run_sw else None
        _, ders = bending_deflection
        af = airfoil
        wing_offset = offset
        c = self.upr - self.lwr
        t = thickness_percent
        twist = twist_degs

        for i in np.arange(0, self.resolution, np.round(self.resolution / 25), dtype=np.int):
            theta = ders[1, i] * pi / 180
            xc = self.x_coords[i] + wing_offset
            yc = self.upr[i]
            zc = ders[0, i]
            res = af.place(c[i], t[i], twist[i], theta, xc, yc, zc)
            res_s = np.copy(res)

            # Do SW shift
            res_s[:, 1] = res[:, 2]
            res_s[:, 2] = res[:, 1]

            filename = os.path.join(path, f'Wing/WingSection{i}.txt')
            np.savetxt(filename, res_s * 39.3701, delimiter='\t')
            if run_sw:
                sw.insert_curve_file(filename)


class Airfoil:
    def __init__(self, file, header_lines, flip=False):
        self.base_af = np.genfromtxt(file, skip_header=header_lines)
        self.base_af = np.append(self.base_af, [self.base_af[0]], axis=0)
        if flip:
            self.base_af[:, 0] *= -1

    def place(self, chord, thickness, twist, angle, x, y, z):
        coords = np.zeros((len(self.base_af), 3))
        coords[:, 1:] = self.base_af * chord
        coords[:, 2] *= thickness

        twist_matrix = [[np.cos(twist), np.sin(twist)], [-np.sin(twist), np.cos(twist)]]
        for row_idx in range(len(coords)):
            coords[row_idx, [1, 2]] = np.matmul(coords[row_idx, [1, 2]], twist_matrix)

        rotation_matrix = [[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]]
        for row_idx in range(len(coords)):
            coords[row_idx, [0, 2]] = np.matmul(coords[row_idx, [0, 2]], rotation_matrix)

        coords += [x, y, z]

        return coords


class Nacelle:
    def __init__(self, area, hub_radius, length, width, percent_drop, resolution=1000):
        self.area = area
        self.a = length
        self.nacelle_width = width
        self.r = hub_radius
        self.percent_drop = percent_drop
        self.resolution = resolution
        self.R = np.sqrt(self.area / np.pi + self.r ** 2)
        self.R_outer = self.R + width

    def _local_radius(self, x, r):
        return np.sqrt(r ** 2 * (1 - (x ** 2 * (1 - self.percent_drop ** 2)) / (self.a ** 2)))

    def _place(self, percent_y, xf, yf, zf, toe_in, r0):
        r = self._local_radius(percent_y * self.a, r0)
        points = np.zeros((self.resolution, 3))

        theta = np.linspace(0, 2 * np.pi, self.resolution)
        points[:, 0] = r * np.cos(theta) * np.cos(toe_in)
        points[:, 1] = r * np.cos(theta) * np.sin(toe_in)
        points[:, 2] = r * np.sin(theta)

        points[:, 0] += xf + percent_y * self.a * np.sin(toe_in)
        points[:, 1] += yf - percent_y * self.a * np.cos(toe_in)
        points[:, 2] += zf

        return points

    def place_outer(self, percent, xf, yf, zf, toe_in):
        return self._place(percent, xf, yf, zf, toe_in, self.R_outer)

    def place_inner(self, percent, xf, yf, zf, toe_in):
        return self._place(percent, xf, yf, zf, toe_in, self.R)

    def save_files(self, sections, xf, yf, zf, toe_in, run_sw=False):
        sw = SolidWorks() if run_sw else None

        def run_save(res, the_type, idx):
            res_o = np.copy(res)
            res_o[:, 1] = res[:, 2]
            res_o[:, 2] = res[:, 1]

            filename_o = os.path.join(global_path, f'Nacelle/Nacelle{the_type}{idx}.txt')

            np.savetxt(filename_o, res_o * 39.3701, delimiter='\t')

            if run_sw:
                sw.insert_curve_file(filename_o)

        i = 0
        for percent in np.linspace(0, 1, sections):
            run_save(self.place_outer(percent, xf, yf, zf, toe_in), 'outer', i)

        i = 0
        for percent in np.linspace(0, 1, sections):
            run_save(self.place_inner(percent, xf, yf, zf, toe_in), 'inner', i)
