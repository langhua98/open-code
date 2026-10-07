---
name: documents
description: 读取或生成 PDF、Word、Excel、PPT 文件，以及画图表。用户要处理 .pdf .docx .xlsx .csv .pptx 文件、做表格或报告、把数据画成图时使用。
---

# 文档和图表

已经装好的 Python 库：

| 文件 | 库（import 名） | 读 | 写 |
| --- | --- | --- | --- |
| PDF | pypdf（`pypdf`） | `PdfReader(路径).pages[i].extract_text()` | `PdfWriter()`：合并、拆分、旋转 |
| Word | python-docx（`docx`） | `Document(路径).paragraphs`、`.tables` | `Document()` 后 `add_heading`、`add_paragraph`、`add_table`，最后 `save` |
| Excel / CSV | pandas、openpyxl | `pd.read_excel`、`pd.read_csv` | `df.to_excel(路径, index=False)`；要格式就用 openpyxl |
| PPT | python-pptx（`pptx`） | `Presentation(路径).slides` | `Presentation()` 后 `slides.add_slide`，最后 `save` |
| 图表 | matplotlib | | `plt.savefig("outputs/图.png", dpi=150, bbox_inches="tight")` |

做法：

1. 写一个小 Python 脚本完成任务并运行。生成后重新读一遍文件，确认内容和格式是对的。
2. 中文：matplotlib 默认字体显示不了中文，会变成方块。图里有中文时，先设置 `plt.rcParams["font.family"] = "WenQuanYi Zen Hei"`（这个中文字体已经装好）。
3. 生成的文件放到 `outputs/`（不提交到 git），告诉用户完整路径。用户可以在 Codespace 左侧的文件列表里，长按或右键文件选择「下载」。
4. 扫描版 PDF 里是图片，`extract_text` 读不出字。这种情况要先告诉用户，需要另外装 OCR 工具。
