/*
  Purpose:
    Temporarily use station_name as flow for enabled directory bindings.

  Background:
    The upload code sends the configured flow together with the file.
    This script makes current real directory rows stop sending UNKNOWN.

  Scope:
    - Only enabled rows
    - Only rows whose flow is UNKNOWN
    - Only rows with non-empty station_name
    - Disabled test rows are not changed
*/

BEGIN TRANSACTION;

UPDATE QMS.dbo.station_directory_config
SET flow = station_name,
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE enabled = 1
  AND flow = N'UNKNOWN'
  AND station_name IS NOT NULL
  AND LTRIM(RTRIM(station_name)) <> N'';

SELECT @@ROWCOUNT AS updated_rows;

SELECT id,
       flow,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;

COMMIT TRANSACTION;
