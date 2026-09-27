# Windows 上准备简历的 LaTeX 环境

本项目用 XeLaTeX 编译中文和英文简历。`resume.tex` / `resume-EN.tex`、`resume.cls`、两个 `.sty` 文件、`fonts/` 和仓库根目录的 `.vscode/settings.json` 需要一起复制。字体由项目目录加载，无须单独安装到 Windows 字体库。

## 1. 安装编辑器和 TeX

1. 安装 [Cursor Windows 用户版](https://cursor.com/download)。已有 VS Code 也可以使用；下文操作相同。
2. 在 Cursor 的扩展市场安装 **LaTeX Workshop**（发布者 James Yu）。扩展的[安装说明](https://github.com/James-Yu/LaTeX-Workshop/wiki/Install)要求 TeX 命令位于系统 `PATH` 中。
3. 按 [TinyTeX 官方 Windows 安装说明](https://yihui.org/tinytex/)下载 `install-bin-windows.bat`，保存后运行。默认安装在 `%APPDATA%\TinyTeX`；安装脚本需要 PowerShell。建议使用当前用户安装，不依赖管理员权限。
4. 关闭并重新打开 Cursor 和终端。在 PowerShell 中确认命令可用：

   ```powershell
   Get-Command xelatex, latexmk, tlmgr
   xelatex --version
   latexmk -v
   ```

如果公司电脑已经安装了 TeX Live/TinyTeX，无须重复安装；只要上面的命令可用即可。MiKTeX 也能使用，但 LaTeX Workshop 的[官方说明](https://github.com/James-Yu/LaTeX-Workshop/wiki/Install)指出，MiKTeX 使用 `latexmk` 时还需要单独安装 Perl，因此这里优先选 TinyTeX。

## 2. 安装简历所需宏包

首次使用时，在 PowerShell 中执行：

```powershell
tlmgr install xltxtra xifthen progressbar hyperref fontawesome geometry titlesec enumitem nth xecjk setspace cite fontspec latexmk pgf ctex
```

TinyTeX 只预装部分宏包。若构建提示 `File 'xxx.sty' not found`，用 `tlmgr search --file "/xxx.sty"` 查所属宏包，再用 `tlmgr install 宏包名` 安装。宏包管理方式见 [TinyTeX 官方说明](https://yihui.org/tinytex/)。首次安装需要能访问 TeX 镜像；之后正常编译可离线完成。

## 3. 在 Cursor 中编译、预览和导出

1. 用 Cursor **打开整个 `interview-guide` 仓库目录**，不要只打开 `resume/`，这样仓库根目录的 `.vscode/settings.json` 才会生效。
2. 打开 `IV-arena/resume/resume.tex`，按 **Ctrl+Alt+B** 构建；英文版则打开 `resume-EN.tex` 构建。
3. 按 **Ctrl+Alt+V** 打开 LaTeX Workshop 内置 PDF 预览。也可以在文件树中打开生成的 `resume.pdf`。
4. 构建时 PDF 已自动导出到 `IV-arena/resume/resume.pdf`；英文版是 `resume-EN.pdf`。发送简历时直接复制对应 PDF。

构建配置由 `resume/.latexmkrc` 决定：XeLaTeX 编译，PDF 留在 `resume/`，`.aux`、`.log`、`.xdv` 等辅助文件进入 `resume/build/`。为了不在根目录生成 `.synctex.gz`，此配置不生成 SyncTeX；普通 PDF 预览不受影响，但源码与 PDF 的双向定位不可用。

不用编辑器时，也可以在 PowerShell 中进入简历目录运行：

```powershell
cd .\IV-arena\resume
latexmk resume.tex
latexmk resume-EN.tex
```

`.latexmkrc` 会自动应用相同的输出位置；不需要额外写 `-xelatex` 或 `-outdir`。

## 4. 验证与排查

- 构建成功后检查 `resume.pdf` 是否存在，并确认 `build/resume.log` 没有以 `!` 开头的 LaTeX 错误。Cursor 的状态应显示 `Recipe succeeded`。
- 若 Cursor 显示 `latexmk` / `xelatex` 找不到，先重新打开 Cursor，再在 PowerShell 运行 `Get-Command xelatex, latexmk`；LaTeX Workshop 不会替你修改 `PATH`。
- 若提示找不到 `FontAwesome` 或 Adobe 中文字体，确认 `fonts/` 被完整复制，且从 `resume/` 目录运行命令行构建。项目使用相对路径加载这些字体。
- 若“问题”面板仍显示旧错误，重新构建后再看 `build/resume.log`。字体形状或 PDF 书签的 warning 不等于构建失败；以 `Recipe succeeded` 和 PDF 实际内容为准。
- 若 `resume/` 根目录出现新的 `.aux`、`.log` 或 `.synctex.gz`，检查是否在仓库根目录打开 Cursor，以及构建配方是否为 `latexmk (latexmkrc)`。直接运行 `xelatex resume.tex` 不会读取 `.latexmkrc`。
- `.tex` 首行的 `% !LW recipe=latexmk (latexmkrc)` 指定项目配方；不要改回 `% !TEX TS-program = xelatex`，后者会让 LaTeX Workshop 直接调用 `xelatex`，绕过辅助目录配置。

Windows 上的快捷键及输出路径可参考 LaTeX Workshop 的[编译说明](https://github.com/James-Yu/LaTeX-Workshop/wiki/Compile)和[预览说明](https://github.com/James-Yu/LaTeX-Workshop/wiki/View)。
