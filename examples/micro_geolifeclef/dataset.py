from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from PIL import Image

from torch.utils.data import Dataset

from malpolon.data.environmental_raster import PatchExtractor


def load_patch(
    observation_id,
    patches_path,
    *,
    data="all",
    return_arrays=True,
):
    """Loads the patch data associated to an observation id.

    Parameters
    ----------
    observation_id : integer / string
        Identifier of the observation.
    patches_path : string / pathlib.Path
        Path to the folder containing all the patches.
    data : string or list of string
        Specifies what data to load, possible values: 'all', 'rgb', 'near_ir', 'landcover' or 'altitude'.
     return_localisation : boolean
        If True, returns also the localisation as a tuple (latitude, longitude)
    return_arrays : boolean
        If True, returns all the patches as Numpy arrays (no PIL.Image returned).

    Returns
    -------
    patches : dict containing 2d array-like objects
        Returns a dict containing the requested patches.
    """
    filename = Path(patches_path) / str(observation_id)

    patches = {}

    if data == "all":
        data = ["rgb", "near_ir", "landcover", "altitude"]

    if "rgb" in data:
        rgb_filename = filename.with_name(filename.stem + "_rgb.jpg")
        rgb_patch = Image.open(rgb_filename)
        if return_arrays:
            rgb_patch = np.asarray(rgb_patch)
        patches["rgb"] = rgb_patch

    if "near_ir" in data:
        near_ir_filename = filename.with_name(filename.stem + "_near_ir.jpg")
        near_ir_patch = Image.open(near_ir_filename)
        if return_arrays:
            near_ir_patch = np.asarray(near_ir_patch)
        patches["near_ir"] = near_ir_patch

    if "altitude" in data:
        altitude_filename = filename.with_name(filename.stem + "_altitude.tif")
        altitude_patch = tifffile.imread(altitude_filename)
        patches["altitude"] = altitude_patch

    if "landcover" in data:
        landcover_filename = filename.with_name(filename.stem + "_landcover.tif")
        landcover_patch = tifffile.imread(landcover_filename)
        patches["landcover"] = landcover_patch

    return patches


class MicroGeoLifeCLEF2022Dataset(Dataset):
    """Pytorch dataset handler for a subset of GeoLifeCLEF 2022 dataset.
    It consists in a restriction to France and to the 100 most present plant species.

    Parameters
    ----------
    root : string or pathlib.Path
        Root directory of dataset.
    subset : string, either "train", "val", "train+val" or "test"
        Use the given subset ("train+val" is the complete training data).
    patch_data : string or list of string
        Specifies what type of patch data to load, possible values: 'all', 'rgb', 'near_ir', 'landcover' or 'altitude'.
    use_rasters : boolean (optional)
        If True, extracts patches from environmental rasters.
    patch_extractor : PatchExtractor object (optional)
        Patch extractor to use if rasters are used.
    use_localisation : boolean
        If True, returns also the localisation as a tuple (latitude, longitude).
    transform : callable (optional)
        A function/transform that takes a list of arrays and returns a transformed version.
    target_transform : callable (optional)
        A function/transform that takes in the target and transforms it.
    """

    def __init__(
        self,
        root,
        subset,
        *,
        patch_data="all",
        use_rasters=True,
        patch_extractor=None,
        use_localisation=False,
        transform=None,
        target_transform=None,
    ):
        root = Path(root)

        self.root = root
        self.subset = subset
        self.patch_data = patch_data
        self.use_localisation = use_localisation
        self.transform = transform
        self.target_transform = target_transform
        self.training = (subset != "test")
        self.n_classes = 10

        df = pd.read_csv(
            root / "micro_geolifeclef_observations.csv",
            sep=";",
            index_col="observation_id",
        )

        if subset not in ["train+val", "test"]:
            ind = df.index[df["subset"] == subset]
            df = df.loc[ind]

        self.observation_ids = df.index
        self.coordinates = df[["latitude", "longitude"]].values

        if self.training:
            self.targets = df["species_id"].values
        else:
            self.targets = None

        if use_rasters:
            if patch_extractor is None:
                patch_extractor = PatchExtractor(self.root / "rasters", size=256)
                patch_extractor.add_all_rasters()

            self.patch_extractor = patch_extractor
        else:
            self.patch_extractor = None

    def __len__(self):
        """Returns the number of observations in the dataset."""
        return len(self.observation_ids)

    def __getitem__(self, index):
        latitude = self.coordinates[index][0]
        longitude = self.coordinates[index][1]
        observation_id = self.observation_ids[index]

        patches = load_patch(
            observation_id, self.root / "patches", data=self.patch_data
        )

        # Extracting patch from rasters
        if self.patch_extractor is not None:
            environmental_patches = self.patch_extractor[(latitude, longitude)]
            patches["environmental_patches"] = environmental_patches

        if self.use_localisation:
            patches["localisation"] = np.asarray([latitude, longitude], dtype=np.float32)

        if self.transform:
            patches = self.transform(patches)

        if self.training:
            target = self.targets[index]

            if self.target_transform:
                target = self.target_transform(target)

            return patches, target
        else:
            return patches