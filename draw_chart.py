"""
图表生成模块 - 基于 Pillow 绘制排行榜柱状图和注入量折线图

字体使用插件目录下 fonts/SIMYOU.TTF（华文细黑），
输出为 PNG 格式的 bytes，上游通过 base64 编码后经 MaiBot send_api 发送。
"""

import random
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont


class DrawBarChart:
    """Pillow 图表绘制类，包含柱状图和折线图两种绘制方法"""

    def __init__(self) -> None:
        self.colors: List[Tuple[int, int, int]] = [
            (31, 119, 180),
            (44, 160, 44),
            (214, 39, 40),
            (255, 127, 14),
            (148, 103, 189),
            (23, 190, 207),
            (188, 189, 34),
            (227, 119, 194),
            (255, 99, 71),
            (255, 215, 0),
        ]
        module_path = Path(__file__).parent
        self.font = str(module_path / "fonts" / "SIMYOU.TTF")

    async def draw_bar_chart(self, data: Dict[str, float]) -> bytes:
        """绘制排行榜柱状图，1920×1080 画布，上下双方向柱子"""
        values = list(data.values())
        keys = list(data.keys())
        image = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 绘制半透明白色背景卡片（模糊玻璃效果）
        image_new = Image.new("RGBA", (1920, 1080), (255, 255, 255, 0))
        draw_new = ImageDraw.Draw(image_new)
        draw_new.rectangle((420, 25, 1860, 1060), fill=(255, 255, 255, 220))
        image_new = image_new.filter(ImageFilter.GaussianBlur(radius=0.1))
        image.paste(image_new, (0, 0), image_new)

        # 坐标轴：横轴 y=770，纵轴 x=500
        draw.line((490, 770, 1800, 770), fill="black", width=2)
        draw.line((500, 50, 500, 1030), fill="black", width=2)
        maxnum_scale = abs(max(values) / 9)
        minnum_scale = abs(min(values) / 3)

        def draw_dotted_line(y):
            """在 y 位置画水平虚线"""
            x_start, x_end = 500, 1800
            dash_length = 10
            gap_length = 5
            x = x_start
            while x < x_end:
                x_dash_end = min(x + dash_length, x_end)
                draw.line((x, y, x_dash_end, y), fill="black", width=1)
                x += dash_length + gap_length

        # 上下各 10 条刻度虚线
        for i in range(10):
            draw_dotted_line(770 - 780 * i / 10)
            draw_dotted_line(770 + 780 * i / 10)
        maxnum_scale = int(maxnum_scale / 50 + 1) * 50
        minnum_scale = int(minnum_scale / 50 + 1) * 50

        if maxnum_scale == 0:
            maxnum_scale = 50
        if minnum_scale == 0:
            minnum_scale = 50
        # 正向刻度标签
        for i in range(10):
            draw.text(
                (450, 770 - 780 * i / 10 - 10),
                str(maxnum_scale * i),
                fill="black",
                font=ImageFont.truetype(self.font, 20),
            )
        # 负向刻度标签
        for i in range(1, 4):
            draw.text(
                (450, 770 + 780 * i / 10 - 10),
                f"-{str(minnum_scale * i)}",
                fill="black",
                font=ImageFont.truetype(self.font, 20),
            )

        # 左侧图例 + 柱子绘制
        columns = Image.new("RGBA", (1920, 1080), (255, 255, 255, 0))
        draw = ImageDraw.Draw(columns)
        random.shuffle(self.colors)
        for i, value in enumerate(values):
            color = self.colors[i]
            draw.rectangle((50, 50 + 70 * i, 100, 100 + 70 * i), fill=color + (250,))
            draw.text(
                (120, 60 + 70 * i),
                keys[i] if len(keys[i]) < 8 else f"{keys[i][:8]}...",
                fill="black",
                font=ImageFont.truetype(self.font, 28),
            )
            if value > 0:
                draw.rectangle(
                    (540 + 120 * i, 770 - 78 * (value / maxnum_scale), 635 + 120 * i, 770),
                    fill=color + (200,),
                )
                draw.text(
                    (540 + 120 * i, 770 - 78 * (value / maxnum_scale) - 30),
                    str(value),
                    fill="black",
                    font=ImageFont.truetype(self.font, 26),
                )
            else:
                draw.rectangle(
                    (540 + 120 * i, 770, 635 + 120 * i, 770 - 78 * (value / minnum_scale)),
                    fill=color + (200,),
                )
                draw.text(
                    (540 + 120 * i, 770 - 78 * (value / minnum_scale) + 10),
                    str(value),
                    fill="black",
                    font=ImageFont.truetype(self.font, 26),
                )

        image.paste(columns, (0, 0), columns)
        img_byte = BytesIO()
        image.save(img_byte, format="PNG")
        return img_byte.getvalue()

    async def draw_line_chart(self, data: Dict[str, float]) -> bytes:
        """绘制注入量趋势折线图，1920×1080 画布
        单数据点走独立精简分支（避免折线图除零错误）
        """
        values = list(data.values())
        keys = list(data.keys())

        # 单点分支：正中绘制一个圆点 + 左侧文字标注
        if len(values) == 1:
            image = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))
            draw = ImageDraw.Draw(image)
            draw.line((490, 540, 1800, 540), fill="black", width=2)
            draw.line((500, 50, 500, 1030), fill="black", width=2)
            x_center = 960
            y = 540
            draw.ellipse((x_center - 8, y - 8, x_center + 8, y + 8), fill="black", width=2)
            draw.text((x_center - 20, y - 40), f"{values[0]}ml", fill="black",
                      font=ImageFont.truetype(self.font, 32))
            draw.text((50, 60), f"{keys[0]}   {values[0]}ml", fill="black",
                      font=ImageFont.truetype(self.font, 34))
            bytes_io = BytesIO()
            image.save(bytes_io, format="PNG")
            return bytes_io.getvalue()

        # 多点分支：完整折线图 + 左侧日期标签
        image = Image.new("RGBA", (1920, 1080), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        # 半透明白色背景
        image_new = Image.new("RGBA", (1920, 1080), (255, 255, 255, 0))
        draw_new = ImageDraw.Draw(image_new)
        draw_new.rectangle((420, 25, 1860, 1060), fill=(255, 255, 255, 220))
        image_new = image_new.filter(ImageFilter.GaussianBlur(radius=0.1))
        image.paste(image_new, (0, 0), image_new)

        # 坐标轴
        draw.line((490, 1000, 1800, 1000), fill="black", width=2)
        draw.line((500, 50, 500, 1030), fill="black", width=2)
        maxnum_scale = max(values) / 9

        def draw_dotted_line(y):
            x_start, x_end = 500, 1800
            dash_length = 10
            gap_length = 5
            x = x_start
            while x < x_end:
                x_dash_end = min(x + dash_length, x_end)
                draw.line((x, y, x_dash_end, y), fill="black", width=1)
                x += dash_length + gap_length

        for i in range(10):
            draw_dotted_line(1000 - 950 * i / 10)
        maxnum_scale = int((maxnum_scale / 20 + 1) * 20)
        if maxnum_scale == 0:
            maxnum_scale = 20

        for i in range(10):
            draw.text(
                (450, 1000 - 950 * i / 10 - 10),
                str(maxnum_scale * i),
                fill="black",
                font=ImageFont.truetype(self.font, 20),
            )

        def draw_line_chart():
            """逐点连线 + 数值标注"""
            x_start = 540
            x_gap = (1800 - x_start) / (len(values) - 1)
            x = x_start
            y = 1000 - 95 * (values[0] / maxnum_scale)
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="black", width=2)
            draw.text(
                (x - 20, y - 30),
                str(values[0]),
                fill="black",
                font=ImageFont.truetype(self.font, 32),
            )
            for i in range(1, len(values)):
                x_new = x_start + x_gap * i
                y_new = 1000 - 95 * (values[i] / maxnum_scale)
                draw.line((x, y, x_new, y_new), fill="black", width=2)
                x, y = x_new, y_new
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill="black", width=2)
                draw.text(
                    (x - 20, y - 30),
                    str(values[i]),
                    fill="black",
                    font=ImageFont.truetype(self.font, 26),
                )

        draw_line_chart()
        if len(values) > 18:
            keys = keys[:9] + keys[-9:]
            values = values[:9] + values[-9:]
        position = 0
        for i in range(len(values)):
            position += 50
            if i == 9:
                draw.text(
                    (50, position),
                    ".........\n.........",
                    fill="black",
                    font=ImageFont.truetype(self.font, 34),
                )
                position += 100
            draw.text(
                (50, position),
                f"{keys[i]}   {values[i]}ml",
                fill="black",
                font=ImageFont.truetype(self.font, 34),
            )
        bytes_io = BytesIO()
        image.save(bytes_io, format="PNG")
        return bytes_io.getvalue()


draw_bar_chart = DrawBarChart()
