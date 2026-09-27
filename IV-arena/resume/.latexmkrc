# 中文简历需要 XeLaTeX；PDF 留在本目录，辅助文件进入 build/。
$pdf_mode = 5;
$xelatex = 'xelatex -interaction=nonstopmode -halt-on-error %O %S';
$out_dir = '.';
$aux_dir = 'build';

# 在 TeX Live/TinyTeX 上模拟独立的辅助目录，兼容 Windows 和 macOS。
$emulate_aux = 1;
