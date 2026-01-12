以下是针对 **mssql-cli** 的常用维护命令和最佳实践总结，结合工具特性与 SQL Server 数据库管理需求，提供高效的操作指南：

---

### **一、mssql-cli 基础使用与维护命令**

#### 1. **安装与连接**

- **安装**：
  ```bash
  pip install mssql-cli  # 通过 Python 的 pip 安装
  ```
- **连接数据库**：
  ```bash
  mssql-cli -S <服务器地址> -d <数据库名> -U <用户名> -P <密码>
  ```

  支持 `-E` 参数使用 Windows 身份验证（仅限 Windows 环境）。

#### 2. **配置文件优化**

- 创建 `~/.mssqlrc` 文件存储常用连接参数，避免重复输入：
  ```ini
  [main]
  server = your_server
  database = your_db
  user = your_user
  password = your_password
  ```
- 通过配置文件快速登录：
  ```bash
  mssql-cli  # 自动读取配置文件
  ```

#### 3. **常用维护操作**

- **查看数据库状态**：
  ```sql
  SELECT name, state_desc FROM sys.databases;  -- 列出所有数据库及其状态
  ```
- **备份与恢复**：
  ```sql
  BACKUP DATABASE [YourDB] TO DISK = '/path/to/backup.bak';  -- 执行完整备份
  RESTORE DATABASE [YourDB] FROM DISK = '/path/to/backup.bak';  -- 恢复数据库
  ```
- **查询执行计划**：
  ```sql
  SET SHOWPLAN_TEXT ON;  -- 开启执行计划显示
  GO
  SELECT * FROM YourTable WHERE YourCondition;
  GO
  ```

  分析执行计划优化查询性能。

---

### **二、最佳实践指南**

#### 1. **高效查询与脚本管理**

- **多行编辑模式**：在交互式命令行中按 `F3` 进入多行编辑模式，便于编写复杂查询。
- **历史记录与自动补全**：使用 `↑/↓` 键调用历史命令，结合自动补全（按 `Tab`）减少输入错误。
- **非交互式脚本执行**：
  通过 `-Q` 参数直接执行 SQL 文件或命令：
  ```bash
  mssql-cli -S localhost -d TestDB -Q "SELECT COUNT(*) FROM Users;"
  ```

#### 2. **性能优化**

- **避免负向条件与前导模糊查询**：如 `NOT IN` 或 `LIKE '%value%'` 可能导致全表扫描，改用 `IN` 或后缀模糊查询 `LIKE 'value%'`。
- **索引管理**：
  ```sql
  CREATE INDEX idx_column ON TableName(ColumnName);  -- 创建索引
  SELECT * FROM sys.indexes WHERE object_id = OBJECT_ID('TableName');  -- 查看索引
  ```
- **使用临时表减少锁竞争**：
  复杂查询的中间结果存入临时表，降低主表锁冲突。

#### 3. **安全与权限管理**

- **最小权限原则**：为维护账号分配仅需的权限（如 `db_backupoperator` 或 `db_datareader`）。
- **审计登录权限**：
  ```sql
  EXEC sp_helplogins;  -- 查看所有登录账号权限
  SELECT * FROM sys.server_permissions;  -- 服务器级权限详情
  ```
- **加密连接**：
  通过 `-N` 参数启用 SSL 加密传输：
  ```bash
  mssql-cli -S server -U user -P password -N
  ```

#### 4. **数据维护与清理**

- **清理历史数据**：
  ```sql
  DELETE FROM LogTable WHERE CreateTime < DATEADD(MONTH, -6, GETDATE());  -- 删除6个月前日志
  ```
- **监控表空间**：
  ```sql
  SELECT 
      DB_NAME(database_id) AS DatabaseName,
      COUNT(*) * 8 / 1024 AS CachedSizeMB
  FROM sys.dm_os_buffer_descriptors
  GROUP BY DB_NAME(database_id);  -- 查看各数据库缓存占用
  ```

---

### **三、工具生态与替代方案**

- **迁移至 go-sqlcmd**：由于 mssql-cli 已进入弃用阶段，建议逐步迁移至 Microsoft 官方推荐的替代工具 `go-sqlcmd`，支持类似功能且长期维护。
- **可视化辅助工具**：
  结合 `Azure Data Studio` 或 `SQL Server Management Studio (SSMS)` 进行复杂操作，mssql-cli 作为轻量级命令行补充。

---

### **四、故障排查与日志分析**

- **查看错误日志**：
  ```sql
  EXEC xp_readerrorlog 0, 1, N'Error';  -- 读取 SQL Server 错误日志
  ```
- **终止阻塞进程**：
  ```sql
  KILL <SPID>;  -- 终止指定会话 ID
  ```

---

通过上述实践，可显著提升 mssql-cli 在 SQL Server 维护中的效率与安全性。建议定期检查工具更新并关注官方迁移指南，确保与最新技术栈兼容。
