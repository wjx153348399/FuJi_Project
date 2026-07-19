USE QMS;

IF OBJECT_ID(N'dbo.zk_upload_task_queue', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.zk_upload_task_queue (
        id BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        status NVARCHAR(30) NOT NULL,
        run_id NVARCHAR(80) NOT NULL,
        flow NVARCHAR(50) NULL,
        filePath NVARCHAR(1000) NULL,
        filename NVARCHAR(255) NULL,
        full_path NVARCHAR(1000) NOT NULL,
        business_key NVARCHAR(500) NULL,
        fallback_key NVARCHAR(1000) NULL,
        dedupe_key NVARCHAR(1000) NULL,
        request_json NVARCHAR(MAX) NULL,
        response_json NVARCHAR(MAX) NULL,
        error_message NVARCHAR(MAX) NULL,
        http_status INT NULL,
        retry_count INT NOT NULL DEFAULT 0,
        source_hash CHAR(64) NOT NULL,
        created_at DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
        started_at DATETIME2 NULL,
        finished_at DATETIME2 NULL
    );
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'UX_zk_upload_task_queue_source_hash'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_task_queue')
)
BEGIN
    CREATE UNIQUE INDEX UX_zk_upload_task_queue_source_hash
    ON dbo.zk_upload_task_queue (source_hash);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_zk_upload_task_queue_status_created'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_task_queue')
)
BEGIN
    CREATE INDEX IX_zk_upload_task_queue_status_created
    ON dbo.zk_upload_task_queue (status, created_at, id);
END;

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_zk_upload_task_queue_full_path'
      AND object_id = OBJECT_ID(N'dbo.zk_upload_task_queue')
)
BEGIN
    CREATE INDEX IX_zk_upload_task_queue_full_path
    ON dbo.zk_upload_task_queue (full_path);
END;
