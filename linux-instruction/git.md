以下是 Git 日常开发维护的常用命令和最佳实践，帮助提高代码管理效率和团队协作质量：

---

### **一、日常高频命令**

#### 1. 仓库初始化与克隆

```bash
git init                  # 初始化本地仓库
git clone <url>           # 克隆远程仓库
```

#### 2. 提交与修改

```bash
git add <file>            # 添加文件到暂存区
git add .                 # 添加所有修改到暂存区
git commit -m "message"   # 提交暂存区内容
git commit --amend        # 修改最近一次提交（不产生新提交记录）
```

#### 3. 分支管理

```bash
git branch                # 查看本地分支
git branch <name>         # 创建新分支
git checkout <branch>     # 切换到分支
git checkout -b <branch>  # 创建并切换到新分支
git branch -d <branch>    # 删除本地分支（安全删除）
git branch -D <branch>    # 强制删除本地分支（未合并时）
git push origin --delete <branch> # 删除远程分支
```

#### 4. 同步与拉取代码

```bash
git pull origin <branch>  # 拉取远程分支并合并（等价于 fetch + merge）
git pull --rebase         # 拉取代码并变基（保持提交线性）
git fetch                 # 仅获取远程变更，不自动合并
```

#### 5. 合并与变基

```bash
git merge <branch>        # 合并指定分支到当前分支
git rebase <branch>       # 变基当前分支到目标分支（整理提交历史）
git rebase -i HEAD~n      # 交互式变基（合并/修改最近n次提交）
```

#### 6. 撤销与恢复

```bash
git restore <file>        # 撤销工作区修改（未 add）
git restore --staged <file> # 撤销暂存区修改（已 add）
git reset HEAD~1          # 回退到上一次提交（保留修改）
git reset --hard HEAD~1   # 强制回退到上一次提交（丢弃修改）
```

#### 7. 查看状态与历史

```bash
git status                # 查看工作区状态
git log                   # 查看提交历史
git log --oneline --graph # 图形化简洁历史
git diff                  # 查看未暂存的修改
git diff --cached         # 查看已暂存的修改
```

---

### **二、最佳实践指南**

#### 1. 分支策略

- **主分支保护**：`main`/`master` 分支仅用于发布稳定版本，禁止直接提交。
- **功能分支**：新功能开发使用 `feature/xxx` 分支，合并前发起 Pull Request (PR)。
- **修复分支**：紧急 Bug 使用 `hotfix/xxx` 分支，测试后合并到主分支。
- **命名规范**：分支名清晰描述用途，如 `feat/user-auth` 或 `fix/login-error`。

#### 2. 提交规范

- **原子性提交**：每个提交只做一件事（例如修复一个 Bug 或新增一个功能）。
- **清晰的提交信息**：使用 [Conventional Commits](https://www.conventionalcommits.org/) 规范：
  ```
  feat: 添加用户登录功能
  fix: 修复支付接口超时问题
  docs: 更新 API 文档
  chore: 升级依赖版本
  ```
- **避免大提交**：频繁提交小修改，便于回滚和代码审查。

#### 3. 合并与冲突处理

- **合并前先拉取代码**：执行 `git pull --rebase` 保持本地分支与远程同步。
- **优先使用 rebase**：本地开发分支定期变基主分支，保持提交历史线性。
- **解决冲突后验证**：手动解决冲突后运行测试，确保功能正常。

#### 4. 远程仓库维护

- **定期清理分支**：合并后删除已废弃的本地和远程分支。
- **使用标签（Tag）**：发布版本时打标签 `git tag v1.0.0 && git push origin --tags`。
- **忽略文件**：通过 `.gitignore` 排除临时文件（如日志、编译产物）。

#### 5. 团队协作

- **Code Review**：通过 Pull Request 或 Merge Request 进行代码审查。
- **保护主分支**：设置分支保护规则（如 GitHub 的 Protected Branches）。
- **定期同步**：每天开始工作前执行 `git fetch` 查看远程变更。

在 Git 中保存登录密码（或凭证）可以通过配置 **凭证存储（Credential Storage）** 实现，避免每次推送或拉取代码时重复输入账号密码。以下是具体操作方法和注意事项：

---

## **三、访问权限**

### **1. 配置凭证存储方式**

根据操作系统和需求选择以下一种方式：

#### **方式一：缓存凭证（临时保存）**

```bash
# 将凭证缓存到内存中，默认保存15分钟（单位：秒）
git config --global credential.helper 'cache --timeout=3600'  # 缓存1小时
```

#### **方式二：永久保存到文件（明文存储）**

```bash
# 将凭证明文存储在 ~/.git-credentials 文件中（适合个人开发环境）
git config --global credential.helper 'store'
```

#### **方式三：使用系统安全存储（推荐）**

- **Windows**：使用 `Git Credential Manager`（默认已集成在 Git for Windows 中）
  ```bash
  git config --global credential.helper 'manager-core'
  ```
- **macOS**：使用钥匙串（Keychain）
  ```bash
  git config --global credential.helper 'osxkeychain'
  ```
- **Linux**：使用 `libsecret` 或 `gnome-keyring`
  ```bash
  git config --global credential.helper 'cache --timeout=3600'  # 或安装 gnome-keyring
  ```

---

### **2. 验证配置**

检查当前生效的凭证存储方式：

```bash
git config --global credential.helper
```

---

### **3. 首次使用自动保存**

当第一次执行 `git pull` 或 `git push` 时，输入账号密码后凭证会自动保存，后续操作无需重复输入。

---

### **4. 修改远程仓库 URL 包含用户名（可选）**

如果远程仓库 URL 未包含用户名，可以修改 URL 直接嵌入用户名：

```bash
git remote set-url origin https://username@github.com/username/repo.git
```

后续操作只需输入密码（若未配置凭证存储）。

---

### **5. 安全注意事项**

- **明文存储风险**：使用 `store` 方式时，密码以明文形式保存在 `~/.git-credentials` 文件中，需确保文件权限安全（仅用户可读）。
- **清除凭证**：
  ```bash
  # 删除明文存储的凭证文件
  rm ~/.git-credentials

  # 清除缓存
  git credential-cache exit
  ```

---

### **6. 针对特定仓库配置**

若需为某个仓库单独设置凭证，去掉 `--global` 参数：

```bash
cd /path/to/repo
git config credential.helper 'store'  # 仅对该仓库生效
```

---

### **总结**

- **推荐方式**：优先使用系统安全存储（如 Windows 的 `manager-core` 或 macOS 的 `osxkeychain`）。
- **临时开发**：使用 `cache` 缓存凭证，避免长期存储敏感信息。
- **强制要求**：若团队使用 HTTPS 协议且需频繁操作，配置凭证存储能显著提升效率。

通过以上配置，即可实现 Git 自动保存和复用登录凭证。
