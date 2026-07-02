/*
  Purpose:
    Temporarily use station_name as station_code for enabled directory bindings.

  Background:
    The upload code already sends the configured station_code together with the file.
    Before the backend confirms the final field/value mapping, this script makes
    current real directory rows stop sending UNKNOWN.

  Scope:
    - Only enabled rows
    - Only rows whose station_code is UNKNOWN
    - Only rows with non-empty station_name
    - Disabled test rows are not changed
*/

BEGIN TRANSACTION;

UPDATE QMS.dbo.station_directory_config
SET station_code = station_name,
    updated_by = N'web-confirm',
    updated_at = SYSDATETIME()
WHERE enabled = 1
  AND station_code = N'UNKNOWN'
  AND station_name IS NOT NULL
  AND LTRIM(RTRIM(station_name)) <> N'';

SELECT @@ROWCOUNT AS updated_rows;

SELECT id,
       station_code,
       station_name,
       directory_path,
       enabled,
       sort_order,
       remark,
       updated_at
FROM QMS.dbo.station_directory_config
ORDER BY enabled DESC, sort_order ASC, id ASC;

COMMIT TRANSACTION;
