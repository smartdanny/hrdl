import numpy as np
import pandas as pd
import torch
import torchvision
from tqdm.notebook import tqdm
import glob
import re
from itertools import zip_longest
import random
# from skimage import io
from PIL import Image

class DownstreamTrainingDataset(torch.utils.data.Dataset):

    def __init__(self, root_dir, transform=None, dataset_type="train", group_size=5, subset_size=None, min_patches_per_patient=0):
        """
        Args:
            root_dir (sting): Directory with all the data (eg '/tcmldrive/databases/Public/TCGA/data/')
            transform (callable, optional): Optional transform to be applied on a sample.
            dataset_type (string): "train" or "val"
            subset_size: percentage of dataset I want to use (implemented dueto memory restrictions)
        """
        print('\tInitializing Downstream Training Dataset...')
        self.subset_size = subset_size
        self.transform = transform
        self.group_size = group_size
        self.min_patches_per_patient = min_patches_per_patient
        self.classes = ["dog", "fish"] #eventually make this inferred from folders
        self.class_to_idx = {"dog":0, "fish":1}
        self.dataset_type = dataset_type
        self.root_dir = root_dir
        self.train_dir = root_dir + 'train'
        self.val_dir = root_dir + 'val'
        self.all_filenames = self.get_all_file_paths()
        # self.ultimate_re = r'train|val|TCGA-\w{2}-\w{4}|/fish/|/dog/'
        self.ultimate_re = r'train|val|img[\d{1}]+|/fish/|/dog/'
        self.dataset_dict_tcga = self.make_dataset_dict()
        # self.remove_patients_with_less_than_min_patches()
        self.check_dataset_dict(self.dataset_dict_tcga)
        self.index_mapping = self.__create_index_mapping__()
        print('\t... done initialization ✅')

    def __len__(self):
        return len(self.index_mapping)


    def __create_index_mapping__(self):
        """
        Maps the dataset_dict into a list that is indexable. Elements
        from this list will be yielded in __getitem__
        """
        train_index_mapping = []
        for class_label in self.classes:
            for patient_id in self.dataset_dict_tcga[self.dataset_type][class_label].keys():

                # split this list of paths in the patient into groups of n
                patient_patches_list = self.dataset_dict_tcga[self.dataset_type][class_label][patient_id]
                # shuffle list (equivalent to random.shuffle, except random.shuffle is in-place)
                patient_patches_list = random.sample(patient_patches_list, len(patient_patches_list))

                #https://stackoverflow.com/questions/1624883/alternative-way-to-split-a-list-into-groups-of-n
                grouped_list = list(zip_longest(*(iter(patient_patches_list),) * self.group_size))
                for group in grouped_list:
                    if None not in group:
                        train_index_mapping.append({
                            "label": self.class_to_idx[class_label], 
                            "patient_id": [patient_id]*self.group_size, 
                            "data_paths": ','.join(group)
                            })

        if self.subset_size is not None:
            og_size = len(train_index_mapping)
            new_size = int(og_size*self.subset_size)
            print(f"\t♻️  using {self.subset_size}% of data for downstream training... ({new_size}/{og_size} samples)")
            train_index_mapping = random.sample(train_index_mapping, new_size)

        return train_index_mapping


    def __getitem__(self, idx):
        # idk why I need dis
        # may be required to make compatible with random split
        if torch.is_tensor(idx):
            idx = idx.tolist()

        # looks like {'label': 'fish', 
        #               'patient_id': 'TCGA-CM-6171', 
        #               'data_paths': ('/workspace/repos/TCGA/data/train/fish/blk-THPNGVSFMQPH-TCGA-CM-6171-01Z-00-DX1.jpg', ... }
        patient_set = self.index_mapping[idx]

        # replace paths in patient set with torch tensor of all the patches
        # tensor should be (NxWxHxC)) where n is batch size (in this case it is self.group_size)
        patches = []
        for path in patient_set['data_paths'].split(','):
            # for path in patient_set['data_paths']:
            patch = Image.open(path)
            patch = self.transform(patch).permute(1, 2, 0) #C,W,H->W,H,C
            patches.append(patch)
        patches_stack = torch.stack(patches)
        # patient_set["data"] = patches_stack
        x = patches_stack
        y = patient_set["label"]
        paths = patient_set["data_paths"]
        return paths, x, y
        # return patient_set['label'], patient_set['patient_id'], patient_set['data_paths'], patient_set['data']


    def remove_patients_with_less_than_min_patches(self):

        # first find patients that dont have enough patches
        bad_patients = []
        for cls in self.classes:
            for patient_id in self.dataset_dict_tcga[self.dataset_type][cls]:
                if len(self.dataset_dict_tcga[self.dataset_type][cls][patient_id]) < self.min_patches_per_patient:
                    bad_patients.append((cls, patient_id, len(self.dataset_dict_tcga[self.dataset_type][cls][patient_id])))

        # now get rid of them
        print(f"Removing these patients: {bad_patients}")
        print(f"\t train dict size before: {len(self.dataset_dict_tcga[self.dataset_type][cls])}")
        for cls, patient, num_patches in bad_patients:
            print(f"\t --- removing: {self.dataset_dict_tcga[self.dataset_type][cls].pop(patient)}")
        print(f"\t train dict size after: {len(self.dataset_dict_tcga[self.dataset_type][cls])}")
        print("... patients removed")


    def get_train_sample_filenames(self):
        """ filenames for all images in train dir"""
        train_img_filenames_fish = glob.glob(self.train_dir+'/fish/*.jpg')
        train_img_filenames_dog = glob.glob(self.train_dir+'/dog/*.jpg')
        all_train_filenames = train_img_filenames_fish + train_img_filenames_dog
        return all_train_filenames

    def get_val_sample_filenames(self):
        """ filenames for all images in val dir"""
        val_img_filenames_fish = glob.glob(self.val_dir+'/fish/*.jpg')
        val_img_filenames_dog = glob.glob(self.val_dir+'/dog/*.jpg')
        all_val_filenames = val_img_filenames_fish + val_img_filenames_dog
        return all_val_filenames

    def get_all_file_paths(self):
        """
        EX: ['/workspace/repos/TCGA/data/train/fish/blk-LISQHHKHDTVS-TCGA-CM-6171-01Z-00-DX1.png', ...]
        length is 192312
        """
        all_filenames = self.get_train_sample_filenames() + self.get_val_sample_filenames()
        return all_filenames

    def get_set_class_patientid(self, path):
        """
        This function will return the set (train/val), class(dog/fish), and patientid for a path.
        EX: '/workspace/repos/TCGA/data/train/fish/blk-LISQHHKHDTVS-TCGA-CM-6171-01Z-00-DX1.png' -> ['train', '/fish/', 'TCGA-CM-6171']
        """
        matches = re.findall(self.ultimate_re, path)
        assert(len(matches)==3), f"There are {len(matches)} matches, but it should be 3"
        return matches



    def make_dataset_dict(self):
        """
        makes a nested dict following the structure below.
        """
        data_dict = {
                "train": {
                    "dog": {
                        # patient_id: [],
                        # patient_id: [],
                        # ...
                        },
                    "fish": {}
                    },
                "val": {
                    "dog": {},
                    "fish": {}
                    }
                }
        for i, path in enumerate(self.all_filenames):
            data_set, data_class, patient_id = self.get_set_class_patientid(path)
            data_class = data_class.replace('/', '') # remove "/" (/dog/ -> dog)
            if patient_id in data_dict[data_set][data_class].keys():
                data_dict[data_set][data_class][patient_id].append(path)
            else:
                data_dict[data_set][data_class][patient_id] = [path]
        
        # now remove all the patients that have less than n patches/files
        # if self.min_patches_per_patient > 0:
        #     for 
        return data_dict

    def check_dataset_dict(self, dataset_dict):
        mss_train_num_patients = len(dataset_dict["train"]["dog"])
        msimut_train_num_patients = len(dataset_dict["train"]["fish"])
        mss_val_num_patients = len(dataset_dict["val"]["dog"])
        msimut_val_num_patients = len(dataset_dict["val"]["fish"])
        f_str = (f"\n\t---\n"
                f"\tnum train mss patients      : {mss_train_num_patients}\n"
                f"\tnum val mss patients       : {mss_val_num_patients}\n"
                f"\tnum train msimut patients   : {msimut_train_num_patients}\n"
                f"\tnum val msimut patients   : {msimut_val_num_patients}\n"
                f"\t---\n")
        print(f_str)
 
