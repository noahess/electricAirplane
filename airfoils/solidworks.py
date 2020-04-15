import win32com.client
import pythoncom


class SolidWorks:
    """
    Uses the exposed Solidworks API interface over win32com to script SolidWorks

    API reference here
    https://help.solidworks.com/2018/english/api/SWHelp_List.html

    Thanks to Joshua Redstone
    http://joshuaredstone.blogspot.com/2015/02/solidworks-macros-via-python.html
    """

    def __init__(self):
        self.sw = win32com.client.Dispatch('SldWorks.Application')
        self.model = None
        self.featureMgr = None
        self.modelExt = None
        self.selMgr = None
        self._select_arg = win32com.client.VARIANT(pythoncom.VT_DISPATCH, None)

    def _select_all(self, name_list: list, clear_all=True):
        """
        Selects all features with name in name_list
        :param name_list: a list of valid feature names
        :param clear_all: True to clear the existing selections
        :return:
        """
        if clear_all:
            self.model.ClearSelection2(True)
        for feature_name in name_list:
            self.modelExt.SelectById2(feature_name, 'REFERENCECURVES', 0, 0, 0, True, 0, self._select_arg, 0)

    def create_new_file(self, filename):
        """
        Creates a new SolidWorks file - untested
        :param filename: the filename to save to
        :return:
        """
        self.sw.NewDocument(filename, 0, 0, 0)
        self.use_current_file()

    def use_current_file(self):
        """
        Connect to an existing SolidWorks document open
        :return:
        """
        self.model = self.sw.ActiveDoc
        self.featureMgr = self.model.FeatureManager
        self.modelExt = self.model.Extension
        self.selMgr = self.model.SelectionManager

    def insert_file_group(self, file_list, hide=True):
        """
        Insert a list of xyz curve text files

        Note: using np.savetxt puts the xyz points into a format SolidWorks accepts

        :param file_list: the list of (full) filenames to import
        :param hide: True to hide the imported curves
        :return: The list of feature names created
        """
        self.featureMgr.EnableFeatureTree = False
        self.model.ClearSelection2(True)

        for file in file_list:
            self.insert_curve_file(file)

        idx = 0
        name_list = []
        for feature in self.featureMgr.GetFeatures(True):
            if feature.GetTypeName == 'CurveInFile' and feature.Name[0:5] == 'Curve':
                file_name = file_list[idx].split('\\')[-1].split('.')[0]
                new_name = f"S-{file_name}"
                name_list.append(new_name)
                feature.Name = new_name

                idx += 1

        if hide:
            self._select_all(name_list)
            self.model.BlankRefGeom()

        self.featureMgr.EnableFeatureTree = True

        return name_list

    def merge_features_to_folder(self, name_list, folder_name):
        """
        Combines the features given in name_list into a folder given by folder_name
        :param name_list: A list of valid feature names
        :param folder_name: The name of the new folder
        :return: the
        """

        self._select_all(name_list)

        new_folder = self.featureMgr.InsertFeatureTreeFolder2(2)
        new_folder.name = folder_name

    def insert_loft(self, list_of_ids, loft_name):
        """
        Inserts a loft through reference curves given by list_of_ids
        :param list_of_ids: A list of valid reference curve names
        :param loft_name: The name of the new loft
        :return: the loft element
        """
        self.featureMgr.EnableFeatureTree = False
        self._select_all(list_of_ids)
        self.model.InsertLoftRefSurface2(False, True, False, 1, 6, 6)

        the_loft = self.selMgr.GetSelectedObject6(1, -1)
        the_loft.name = f"U-{loft_name}"

        self.featureMgr.EnableFeatureTree = True

        return the_loft

    def insert_curve_file(self, filename):
        """
        Inserts a file of xyz curve points into SolidWorks

        Note: using np.savetxt puts the xyz points into a format SolidWorks accepts

        :param filename: The (full) filename to import
        :return:
        """
        self.model.InsertCurveFile(filename)
