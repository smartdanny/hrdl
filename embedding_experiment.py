import torch
# from pytorch_lightning import Trainer
from pytorch_lightning.loggers import WandbLogger
from src.data_stuff.patch_datamodule import TcgaDataModule
# from src.model_stuff.MyResNet import MyResNet

import flash
from flash.image import ImageClassificationData, ImageEmbedder

# --- hypers --- #
batch_size = 16
data_dir = '/home/shatz/repos/data/imagenette_tesselated/'
min_patches_per_patient = 0
# ------------- #

EXP_NAME = f"SIMCLR"
logger=WandbLogger(project="moti_imagenette_tesselated", name=EXP_NAME)
# logger = TensorBoardLogger("./lightning_logs", name=EXP_NAME)

# model = MyResNet()
embedder = ImageEmbedder(
        backbone="resnet",
        training_strategy="barlow_twins",
        head="simclr_head",
        pretraining_transform="barlow_twins_transform",
        training_strategy_kwargs={"latent_embedding_dim": 128},
        pretraining_transform_kwargs={"size_crops": [196]},
)

dm = ImageClassificationData.from_folders(
    train_folder=data_dir+"train/",
    val_folder=data_dir+"val/",
    batch_size=64,
    # transform_kwargs={"image_size": (196, 196), "mean": (0.485, 0.456, 0.406), "std": (0.229, 0.224, 0.225)},
)
# dm = TcgaDataModule(data_dir=data_dir, batch_size=batch_size, fast_subset=False, min_patches_per_patient=min_patches_per_patient)
# class_to_idx = dm.get_class_to_idx_dict()


trainer = flash.Trainer(gpus=1, max_epochs=120,
        logger=logger,
        # callbacks=[
        #     PatientLevelValidation.PatientLevelValidation(),
        #     LogConfusionMatrix.LogConfusionMatrix(class_to_idx),
        #     ]
        )

trainer.fit(embedder, dm)

trainer.save_checkpoint("embedder_model.pt")
