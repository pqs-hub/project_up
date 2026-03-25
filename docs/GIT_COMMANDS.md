# Git/GitHub 常用命令参考

## 📋 目录
- [基础配置](#基础配置)
- [仓库初始化](#仓库初始化)
- [日常操作](#日常操作)
- [分支管理](#分支管理)
- [远程仓库](#远程仓库)
- [查看历史](#查看历史)
- [撤销操作](#撤销操作)
- [标签管理](#标签管理)
- [高级技巧](#高级技巧)
- [常见问题](#常见问题)

---

## 基础配置

### 设置用户信息
```bash
# 设置全局用户名和邮箱
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 查看配置
git config --list
git config user.name
git config user.email
```

### SSH 密钥配置
```bash
# 生成 SSH 密钥
ssh-keygen -t ed25519 -C "your.email@example.com"

# 查看公钥（添加到 GitHub Settings -> SSH Keys）
cat ~/.ssh/id_ed25519.pub

# 测试 SSH 连接
ssh -T git@github.com
```

### 设置默认分支名
```bash
git config --global init.defaultBranch main
```

---

## 仓库初始化

### 创建新仓库
```bash
# 初始化本地仓库
git init

# 初始化并设置默认分支为 main
git init -b main
```

### 克隆远程仓库
```bash
# HTTPS 方式
git clone https://github.com/username/repo.git

# SSH 方式（推荐）
git clone git@github.com:username/repo.git

# 克隆到指定目录
git clone git@github.com:username/repo.git my-folder

# 浅克隆（只克隆最近的历史）
git clone --depth 1 git@github.com:username/repo.git
```

---

## 日常操作

### 查看状态
```bash
# 查看工作区状态
git status

# 简洁模式
git status -s
git status --short
```

### 添加文件
```bash
# 添加指定文件
git add file1.txt file2.txt

# 添加所有修改的文件
git add .
git add -A

# 添加所有 .py 文件
git add *.py

# 交互式添加
git add -p
```

### 提交更改
```bash
# 提交并添加消息
git commit -m "Commit message"

# 提交所有已跟踪的修改文件（跳过 git add）
git commit -am "Commit message"

# 修改最后一次提交
git commit --amend -m "New commit message"

# 修改最后一次提交（不改消息）
git commit --amend --no-edit
```

### 查看差异
```bash
# 查看工作区与暂存区的差异
git diff

# 查看暂存区与最后一次提交的差异
git diff --staged
git diff --cached

# 查看两次提交之间的差异
git diff commit1 commit2

# 查看指定文件的差异
git diff file.txt
```

### 删除文件
```bash
# 删除文件并暂存
git rm file.txt

# 只从 Git 删除，保留本地文件
git rm --cached file.txt

# 删除目录
git rm -r folder/
```

### 移动/重命名文件
```bash
git mv old_name.txt new_name.txt
```

---

## 分支管理

### 查看分支
```bash
# 查看本地分支
git branch

# 查看所有分支（包括远程）
git branch -a

# 查看远程分支
git branch -r

# 查看分支详细信息
git branch -v
git branch -vv  # 显示跟踪的远程分支
```

### 创建分支
```bash
# 创建新分支
git branch feature-branch

# 创建并切换到新分支
git checkout -b feature-branch
git switch -c feature-branch  # 新语法
```

### 切换分支
```bash
# 切换分支
git checkout main
git switch main  # 新语法

# 切换到上一个分支
git checkout -
git switch -
```

### 合并分支
```bash
# 合并指定分支到当前分支
git merge feature-branch

# 禁用快进合并（保留分支历史）
git merge --no-ff feature-branch

# 取消合并
git merge --abort
```

### 删除分支
```bash
# 删除已合并的分支
git branch -d feature-branch

# 强制删除分支
git branch -D feature-branch

# 删除远程分支
git push origin --delete feature-branch
```

### 变基（Rebase）
```bash
# 将当前分支变基到 main
git rebase main

# 交互式变基（修改历史提交）
git rebase -i HEAD~3

# 继续变基
git rebase --continue

# 取消变基
git rebase --abort
```

---

## 远程仓库

### 查看远程仓库
```bash
# 查看远程仓库
git remote -v

# 查看远程仓库详细信息
git remote show origin
```

### 添加远程仓库
```bash
# 添加远程仓库
git remote add origin git@github.com:username/repo.git

# 修改远程仓库 URL
git remote set-url origin git@github.com:username/repo.git

# 删除远程仓库
git remote remove origin
```

### 推送到远程
```bash
# 推送到远程仓库
git push origin main

# 首次推送并设置上游分支
git push -u origin main
git push --set-upstream origin main

# 推送所有分支
git push --all origin

# 强制推送（危险！会覆盖远程历史）
git push -f origin main
git push --force origin main

# 强制推送（更安全，如果远程有新提交会失败）
git push --force-with-lease origin main
```

### 拉取远程更新
```bash
# 拉取并合并
git pull origin main

# 拉取并变基
git pull --rebase origin main

# 只拉取不合并
git fetch origin

# 拉取所有远程分支
git fetch --all
```

---

## 查看历史

### 查看提交历史
```bash
# 查看提交历史
git log

# 单行显示
git log --oneline

# 显示最近 5 条
git log -5
git log --oneline -5

# 显示图形化分支历史
git log --graph --oneline --all

# 显示文件修改统计
git log --stat

# 显示详细差异
git log -p

# 查看指定文件的历史
git log file.txt

# 查看指定作者的提交
git log --author="Name"

# 查看指定时间范围的提交
git log --since="2 weeks ago"
git log --after="2024-01-01" --before="2024-12-31"
```

### 查看提交详情
```bash
# 查看最新提交
git show

# 查看指定提交
git show commit_hash

# 查看指定文件在某次提交的内容
git show commit_hash:file.txt
```

### 查看引用日志
```bash
# 查看所有操作历史（包括已删除的提交）
git reflog

# 查看最近 10 条
git reflog -10
```

---

## 撤销操作

### 撤销工作区修改
```bash
# 撤销指定文件的修改
git checkout -- file.txt
git restore file.txt  # 新语法

# 撤销所有修改
git checkout -- .
git restore .
```

### 撤销暂存
```bash
# 取消暂存指定文件
git reset HEAD file.txt
git restore --staged file.txt  # 新语法

# 取消所有暂存
git reset HEAD
git restore --staged .
```

### 撤销提交
```bash
# 撤销最后一次提交，保留修改在工作区
git reset --soft HEAD~1

# 撤销最后一次提交，保留修改在暂存区
git reset --mixed HEAD~1
git reset HEAD~1  # 默认是 --mixed

# 撤销最后一次提交，丢弃所有修改（危险！）
git reset --hard HEAD~1

# 撤销到指定提交
git reset --hard commit_hash
```

### 恢复已删除的提交
```bash
# 查看引用日志找到提交 hash
git reflog

# 恢复到该提交
git reset --hard commit_hash
```

### 创建反向提交
```bash
# 创建一个新提交来撤销指定提交的更改
git revert commit_hash

# 撤销最近的提交
git revert HEAD
```

---

## 标签管理

### 查看标签
```bash
# 查看所有标签
git tag

# 查看符合模式的标签
git tag -l "v1.*"

# 查看标签详情
git show v1.0.0
```

### 创建标签
```bash
# 创建轻量标签
git tag v1.0.0

# 创建附注标签（推荐）
git tag -a v1.0.0 -m "Version 1.0.0"

# 为历史提交打标签
git tag -a v0.9.0 commit_hash -m "Version 0.9.0"
```

### 推送标签
```bash
# 推送指定标签
git push origin v1.0.0

# 推送所有标签
git push origin --tags
```

### 删除标签
```bash
# 删除本地标签
git tag -d v1.0.0

# 删除远程标签
git push origin --delete v1.0.0
git push origin :refs/tags/v1.0.0
```

---

## 高级技巧

### 暂存工作进度
```bash
# 暂存当前修改
git stash
git stash save "Work in progress"

# 查看暂存列表
git stash list

# 应用最近的暂存
git stash apply

# 应用并删除最近的暂存
git stash pop

# 应用指定的暂存
git stash apply stash@{2}

# 删除暂存
git stash drop stash@{0}

# 清空所有暂存
git stash clear
```

### 搜索内容
```bash
# 在工作区搜索
git grep "search_term"

# 在指定提交中搜索
git grep "search_term" commit_hash

# 显示行号
git grep -n "search_term"
```

### 查找引入 bug 的提交
```bash
# 二分查找
git bisect start
git bisect bad  # 当前版本有问题
git bisect good commit_hash  # 指定一个好的版本

# 测试后标记
git bisect good  # 或 git bisect bad

# 结束查找
git bisect reset
```

### 清理仓库
```bash
# 查看未跟踪的文件
git clean -n

# 删除未跟踪的文件
git clean -f

# 删除未跟踪的文件和目录
git clean -fd

# 删除忽略的文件
git clean -fX

# 删除所有未跟踪的文件（包括忽略的）
git clean -fx
```

### 子模块管理
```bash
# 添加子模块
git submodule add git@github.com:user/repo.git path/to/submodule

# 初始化子模块
git submodule init

# 更新子模块
git submodule update

# 克隆包含子模块的仓库
git clone --recursive git@github.com:user/repo.git

# 更新所有子模块
git submodule update --remote
```

---

## 常见问题

### 1. 修改最后一次提交消息
```bash
git commit --amend -m "New commit message"
```

### 2. 合并多个提交
```bash
# 交互式变基最近 3 个提交
git rebase -i HEAD~3

# 在编辑器中将要合并的提交标记为 squash 或 fixup
```

### 3. 撤销已推送的提交
```bash
# 方法 1: 创建反向提交（推荐）
git revert commit_hash
git push origin main

# 方法 2: 强制推送（危险！会改写历史）
git reset --hard HEAD~1
git push -f origin main
```

### 4. 解决合并冲突
```bash
# 查看冲突文件
git status

# 手动编辑冲突文件，然后：
git add conflicted_file.txt
git commit -m "Resolve merge conflict"

# 或取消合并
git merge --abort
```

### 5. 忽略已跟踪的文件
```bash
# 停止跟踪但保留文件
git rm --cached file.txt

# 添加到 .gitignore
echo "file.txt" >> .gitignore

# 提交更改
git add .gitignore
git commit -m "Stop tracking file.txt"
```

### 6. 查看谁修改了某一行
```bash
git blame file.txt

# 查看指定行范围
git blame -L 10,20 file.txt
```

### 7. 同步 fork 的仓库
```bash
# 添加上游仓库
git remote add upstream git@github.com:original/repo.git

# 拉取上游更新
git fetch upstream

# 合并到本地分支
git checkout main
git merge upstream/main

# 推送到自己的 fork
git push origin main
```

### 8. 删除大文件历史
```bash
# 使用 git filter-branch（不推荐，已废弃）
git filter-branch --tree-filter 'rm -f large_file.bin' HEAD

# 使用 BFG Repo-Cleaner（推荐）
java -jar bfg.jar --delete-files large_file.bin
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 9. 切换远程仓库 URL（HTTPS ↔ SSH）
```bash
# 从 HTTPS 切换到 SSH
git remote set-url origin git@github.com:username/repo.git

# 从 SSH 切换到 HTTPS
git remote set-url origin https://github.com/username/repo.git
```

### 10. 创建空分支
```bash
git checkout --orphan new-branch
git rm -rf .
# 添加新文件并提交
```

---

## 快速参考

### 常用工作流
```bash
# 1. 克隆仓库
git clone git@github.com:username/repo.git
cd repo

# 2. 创建功能分支
git checkout -b feature-branch

# 3. 修改代码并提交
git add .
git commit -m "Add new feature"

# 4. 推送到远程
git push -u origin feature-branch

# 5. 在 GitHub 上创建 Pull Request

# 6. 合并后删除分支
git checkout main
git pull origin main
git branch -d feature-branch
```

### Git 别名（提高效率）
```bash
# 设置别名
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.unstage 'reset HEAD --'
git config --global alias.last 'log -1 HEAD'
git config --global alias.lg "log --graph --oneline --all"

# 使用别名
git st
git co main
git lg
```

---

## 相关资源

- [Git 官方文档](https://git-scm.com/doc)
- [GitHub 文档](https://docs.github.com/)
- [Pro Git 书籍](https://git-scm.com/book/zh/v2)
- [Git 可视化学习](https://learngitbranching.js.org/)
- [GitHub Skills](https://skills.github.com/)

---

## 本项目常用命令

```bash
# 查看状态
git status

# 添加所有改动
git add -A

# 提交
git commit -m "描述改动内容"

# 推送到 GitHub
git push origin main

# 拉取最新代码
git pull origin main

# 查看最近 5 次提交
git log --oneline -5

# 查看远程仓库
git remote -v
```
