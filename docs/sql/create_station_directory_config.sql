CREATE TABLE station_directory_config (
  id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_station_directory_config PRIMARY KEY,
  flow NVARCHAR(50) NOT NULL,
  station_name NVARCHAR(100) NULL,
  directory_path NVARCHAR(500) NOT NULL,
  enabled BIT NOT NULL CONSTRAINT DF_station_directory_config_enabled DEFAULT (1),
  sort_order INT NOT NULL CONSTRAINT DF_station_directory_config_sort_order DEFAULT (0),
  remark NVARCHAR(500) NULL,
  created_by NVARCHAR(50) NULL,
  created_at DATETIME2(0) NOT NULL CONSTRAINT DF_station_directory_config_created_at DEFAULT (SYSDATETIME()),
  updated_by NVARCHAR(50) NULL,
  updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_station_directory_config_updated_at DEFAULT (SYSDATETIME())
);

CREATE UNIQUE INDEX UX_station_directory_config_directory_path
  ON station_directory_config (directory_path);

CREATE INDEX IX_station_directory_config_flow
  ON station_directory_config (flow);

CREATE INDEX IX_station_directory_config_enabled_sort
  ON station_directory_config (enabled, sort_order, id);

EXEC sys.sp_addextendedproperty
  @name = N'MS_Description',
  @value = N'工站目录绑定配置表',
  @level0type = N'SCHEMA', @level0name = N'dbo',
  @level1type = N'TABLE', @level1name = N'station_directory_config';

GO

CREATE TRIGGER TR_station_directory_config_set_updated_at
ON station_directory_config
AFTER UPDATE
AS
BEGIN
  SET NOCOUNT ON;

  UPDATE target
  SET updated_at = SYSDATETIME()
  FROM station_directory_config AS target
  INNER JOIN inserted AS source
    ON target.id = source.id;
END;
