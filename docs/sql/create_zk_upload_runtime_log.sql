USE QMS;

IF OBJECT_ID(N'dbo.zk_upload_runtime_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.zk_upload_runtime_log (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        log_time DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        log_date DATE NOT NULL,
        log_type NVARCHAR(30) NOT NULL,
        level NVARCHAR(20) NOT NULL,
        status NVARCHAR(30) NOT NULL,
        action NVARCHAR(80) NOT NULL,
        run_id NVARCHAR(80) NULL,
        filename NVARCHAR(255) NULL,
        full_path NVARCHAR(1000) NULL,
        flow NVARCHAR(50) NULL,
        http_status INT NULL,
        retry_count INT NULL,
        message NVARCHAR(MAX) NULL,
        raw_json NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME()
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_zk_upload_runtime_log_time'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_runtime_log')
)
BEGIN
    CREATE INDEX IX_zk_upload_runtime_log_time
    ON dbo.zk_upload_runtime_log (log_time DESC);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_zk_upload_runtime_log_type_status_time'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_runtime_log')
)
BEGIN
    CREATE INDEX IX_zk_upload_runtime_log_type_status_time
    ON dbo.zk_upload_runtime_log (log_type, status, log_time DESC);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_zk_upload_runtime_log_date'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_runtime_log')
)
BEGIN
    CREATE INDEX IX_zk_upload_runtime_log_date
    ON dbo.zk_upload_runtime_log (log_date, log_type, status);
END;
