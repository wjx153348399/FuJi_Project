/*
  Purpose:
    Rename QMS.dbo.station_directory_config.station_code to flow.

  Run in a maintenance window after backing up production config.
*/

SELECT COLUMN_NAME,
       DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH,
       IS_NULLABLE
FROM QMS.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'station_directory_config'
  AND COLUMN_NAME IN ('station_code', 'flow')
ORDER BY COLUMN_NAME;

SELECT *
INTO QMS.dbo.station_directory_config_backup_before_flow_20260703
FROM QMS.dbo.station_directory_config;

BEGIN TRANSACTION;

IF COL_LENGTH('QMS.dbo.station_directory_config', 'flow') IS NOT NULL
BEGIN
    THROW 51000, 'flow column already exists, stop migration.', 1;
END;

IF COL_LENGTH('QMS.dbo.station_directory_config', 'station_code') IS NULL
BEGIN
    THROW 51001, 'station_code column does not exist, stop migration.', 1;
END;

EXEC QMS.sys.sp_rename
  'dbo.station_directory_config.station_code',
  'flow',
  'COLUMN';

IF EXISTS (
    SELECT 1
    FROM QMS.sys.indexes
    WHERE object_id = OBJECT_ID('QMS.dbo.station_directory_config')
      AND name = 'IX_station_directory_config_station_code'
)
BEGIN
    EXEC QMS.sys.sp_rename
      'dbo.station_directory_config.IX_station_directory_config_station_code',
      'IX_station_directory_config_flow',
      'INDEX';
END;

COMMIT TRANSACTION;

SELECT COLUMN_NAME,
       DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH,
       IS_NULLABLE
FROM QMS.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'station_directory_config'
ORDER BY ORDINAL_POSITION;

SELECT id,
       flow,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       created_by,
       created_at,
       updated_by,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;
