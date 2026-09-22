from insta360_hack.nodes.create_img_to_3d import CreateImgTo3D
from insta360_hack.nodes.download_model import DownloadModel
from insta360_hack.nodes.export_stl import ExportStl
from insta360_hack.nodes.optimize_image import OptimizeImage
from insta360_hack.nodes.poll import PollLux3D
from insta360_hack.nodes.save_image import SaveImage
from insta360_hack.nodes.upload_image import UploadImage
from insta360_hack.nodes.validate import Validate

NODES = [
    Validate(),
    SaveImage(),
    OptimizeImage(),
    UploadImage(),
    CreateImgTo3D(),
    PollLux3D("poll_mesh", "lux3d_task_id", "mesh_output_urls", "网格生成"),
    ExportStl(),
    PollLux3D("poll_stl", "export_task_id", "export_output_urls", "导出 STL"),
    DownloadModel(),
]
