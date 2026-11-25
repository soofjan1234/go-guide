---
title: 第一次用 Linux（二）创建、修改和删除文件
weight: 23
date: 2026-11-23
draft: false
---

## 二、增：创建目录、文件和备份

现在你已经会用 `pwd` 看自己在哪，用 `ls` 看目录里有什么。接下来，在家目录里建一个练习目录，写一份笔记，再给它留一份备份。

### 我想建一个目录，放这次练习的文件

下面会在家目录创建 `linux-practice`。如果终端提示目录已存在，换一个还没用过的名字再试。最后清理时也用你选的名字。

```bash
mkdir ~/linux-practice && cd ~/linux-practice && pwd
```

`mkdir` 是 **make directory**，意思是创建目录。`&&` 表示左边成功后才执行右边。所以目录建好后才会用 `cd` 进去，最后用 `pwd` 确认当前位置。看到自己在刚创建的目录里，再继续。

接下来建一个 `drafts` 目录放笔记，再建一个 `backup/daily` 目录放备份。

```bash
mkdir drafts
mkdir -p backup/daily
ls
```

`-p` 是 **parents**，表示缺少的上级目录也一起建。`mkdir -p backup/daily` 可以读成「创建 `daily`，如果上面的 `backup` 还没有，就先建它」。

### 我想建一个文件，写一行字进去

```bash
touch notes.txt
ls -l notes.txt
printf 'hello\n' > notes.txt
cat notes.txt
```

- `touch` 可以记成「碰一下文件」。目标不存在时，它会创建一个空文件。目标已经存在时，它会更新时间戳，文件内容照旧。
- `printf` 可以用 **print formatted**（按指定格式输出）来记。`\n` 表示换行。这里的 `>` 把原本要显示在终端的 `hello` 写进 `notes.txt`。如果 `notes.txt` 还不存在，`>` 会先创建它。
- `cat notes.txt` 用来确认刚写进去的内容。你应该会看到一行 `hello`。

### 我想复制一份笔记，或者复制整个目录

```bash
cp -i notes.txt backup/daily/
cp -r backup backup-copy
ls backup/daily
ls backup-copy/daily
```

`cp` 是 **copy**（复制）。把它后面的两个位置从左往右读，**先写要复制的东西，再写复制到哪里**。目标是已有的目录 `backup/daily/`，复制过去的文件仍叫 `notes.txt`。

- `-i` 是 **interactive**（交互式）。如果目标文件已经存在，`cp -i` 会先问你是否覆盖。
- `-r` 是 **recursive**（递归）。把它理解成「顺着目录往里走，每一层都处理」。`cp -r backup backup-copy` 会复制 `backup` 和里面的子目录、文件。

## 三、改：改名字、改内容、改权限

### 我想给笔记改个名字，再放进 `drafts`

```bash
mv -i notes.txt linux-notes.txt
mv -i linux-notes.txt drafts/
ls drafts
```

`mv` 是 **move**（移动），读法和 `cp` 一样，先写从哪来，再写到哪去。

- `mv -i notes.txt linux-notes.txt` 的目标是同一目录下的新文件名，所以效果是改名。
- `mv -i linux-notes.txt drafts/` 的目标是一个目录，所以文件移进去以后还叫 `linux-notes.txt`。
- `-i` 在 `mv` 里也是 **interactive**。如果要覆盖同名文件，命令会先询问。

### 我想改掉文件里的一个词，或者在末尾加一行

想改文件中间的内容，可以用文本编辑器。机器上装了 `nano` 的话，试着把第一行的 `hello` 改成 `hello Linux`。

```bash
nano drafts/linux-notes.txt
```

在 `nano` 里用方向键移动光标。改完按 `Ctrl+O`（字母 O）保存，按回车确认文件名，再按 `Ctrl+X` 退出。如果只想补一行，可以直接在终端操作。

```bash
printf 'learned mv today\n' >> drafts/linux-notes.txt
tail -n 3 drafts/linux-notes.txt
```

`>` 和 `>>` 都能把输出写进文件。区别在于文件已经有内容时怎么处理。

| 符号 | 文件已经存在时会怎样 | 什么时候用 |
| --- | --- | --- |
| `>` | 先清空原内容，再写入 | 写一份全新的内容，或明确想替换整个文件 |
| `>>` | 保留原内容，接着往文件末尾写 | 给笔记或日志补一行 |

这里用 `>>` 保留前面写好的笔记，再用 `tail` 查看最后几行。

### 我想让一个脚本可以直接运行

脚本就是把要执行的命令写进文件。先建一个只有两行的 `practice.sh`，它运行时会显示 `hello from Linux`。

```bash
printf '%s\n' '#!/bin/sh' 'echo hello from Linux' > practice.sh
ls -l practice.sh
chmod u+x practice.sh
ls -l practice.sh
./practice.sh
```

`printf '%s\n'` 把后面的两段文本各写一行。脚本第一行的 `#!/bin/sh` 告诉系统用 `/bin/sh` 来执行后面的命令。

`chmod` 是 **change mode**，平时可以记成「改权限」。`u+x` 拆开读就好。

- `u` 对应 **user**，指文件的所有者。
- `+` 是添加。
- `x` 对应 **execute**，是执行权限。

用 `ls -l` 对比前后两次结果。如果一开始是 `-rw-r--r--`，加完会变成 `-rwxr--r--`，所有者那组多了一个 `x`。最后用 `./practice.sh` 运行当前目录里的脚本。

## 四、删：清理刚才创建的文件

### 我想删掉两个练习文件，再删空目录

现在 `drafts` 里有刚改过的笔记，当前目录还有 `practice.sh`。先用 `ls` 确认文件，再一个个删除。

```bash
ls -l drafts/linux-notes.txt practice.sh
rm -i drafts/linux-notes.txt practice.sh
rmdir drafts
ls
```

- `rm` 是 **remove**（删除）。`rm -i` 会逐个询问，确认提示里的文件名后再同意。用 `rm` 删除的文件通常不会进桌面回收站。
- `rmdir` 是 **remove directory**（删除目录），只删空目录。上一步把笔记删掉以后，`drafts` 就空了。如果 `rmdir` 提示目录还有内容，先用 `ls -la drafts` 看里面还有什么。

### 我想把备份副本连同它里面的东西一起删掉

先运行 `ls -R backup-copy`。`-R` 的 `R` 是大写，会把各层子目录里的内容也列出来。确认里面都是刚才复制出来的文件，再运行下面两条命令。

```bash
rm -r backup-copy
ls
```

这里的小写 `-r` 和 `cp -r` 一样，也是 **recursive**。`rm -r` 会删除 `backup-copy` 和里面的文件、子目录。

这时 `backup` 里还保留着原来的笔记副本。想把本次练习也清理掉，可以先回到家目录，再递归删除练习目录。`rm -ri` 把 `-r` 和 `-i` 合在一起，往下逐层处理，每次删除前都会询问。

```bash
cd ~
ls -R ~/linux-practice
rm -ri ~/linux-practice
ls -d ~/linux-practice
```

如果最后一条 `ls` 提示找不到 `~/linux-practice`，练习目录就已经清理掉了。

### `rm -rf` 是什么意思？

`rm -rf` 可以拆成 `rm -r -f`。

- `-r` 是 **recursive**，往目录深处一层层删。
- `-f` 是 **force**，删除前跳过确认，目标不存在时也会直接跳过。

比如，已经用 `ls -R ~/linux-practice` 确认里面都是这次练习的文件，就可以用 `rm -rf ~/linux-practice` 一次清理整个练习目录。用 `-f` 时，尤其要先看清路径，因为命令不会停下来等你确认。
