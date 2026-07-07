USE [QMS];

IF COL_LENGTH('dbo.station_directory_config', 'path_checked') IS NULL
BEGIN
    EXEC(N'
        ALTER TABLE dbo.station_directory_config
        ADD path_checked bit NOT NULL
            CONSTRAINT DF_station_directory_config_path_checked DEFAULT (0);
    ');
END;

IF COL_LENGTH('dbo.station_directory_config', 'path_exists') IS NULL
BEGIN
    EXEC(N'
        ALTER TABLE dbo.station_directory_config
        ADD path_exists bit NOT NULL
            CONSTRAINT DF_station_directory_config_path_exists DEFAULT (0);
    ');
END;

IF COL_LENGTH('dbo.station_directory_config', 'path_is_dir') IS NULL
BEGIN
    EXEC(N'
        ALTER TABLE dbo.station_directory_config
        ADD path_is_dir bit NOT NULL
            CONSTRAINT DF_station_directory_config_path_is_dir DEFAULT (0);
    ');
END;

IF COL_LENGTH('dbo.station_directory_config', 'path_checked_at') IS NULL
BEGIN
    EXEC(N'
        ALTER TABLE dbo.station_directory_config
        ADD path_checked_at datetime NULL;
    ');
END;

IF COL_LENGTH('dbo.station_directory_config', 'path_check_message') IS NULL
BEGIN
    EXEC(N'
        ALTER TABLE dbo.station_directory_config
        ADD path_check_message nvarchar(500) NULL;
    ');
END;

EXEC(N'
    SELECT
        id,
        flow,
        station_name,
        directory_path,
        enabled,
        sort_order,
        remark,
        updated_at,
        path_checked,
        path_exists,
        path_is_dir,
        path_checked_at,
        path_check_message
    FROM dbo.station_directory_config
    ORDER BY enabled DESC, sort_order ASC, id ASC;
');
