NODE_SPECS = [
    ("validate", "校验输入"),
    ("save_image", "保存参考图"),
    ("plan_cutaway", "整理剖面说明"),
    ("optimize_image", "优化参考图"),
    ("upload_image", "上传优化图"),
    ("create_img_to_3d", "创建图生 3D"),
    ("poll_mesh", "网格生成"),
    ("export_stl", "导出 STL"),
    ("poll_stl", "等待导出"),
    ("download_model", "下载模型"),
]

NODE_NAMES = [name for name, _label in NODE_SPECS]
WORKFLOW_ID = "img-to-3d"
