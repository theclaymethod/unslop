# Import Reliability Review

The nightly import failed six times in May: four failures came from duplicate vendor rows, one came from a malformed date, and one came from a timeout while the warehouse file was still uploading. The storage team expects the timeout rate to fall after the storage move, and the report should cite that forecast before it goes to operations.

The current parser accepts the first vendor row and logs the rest as warnings, which made the dashboard look current even when the warehouse team still needed the rejected rows. A blocking preflight check would make the failure visible before any rows are written.

The proposed fix blocks duplicate vendor IDs before the import writes to the reporting tables, then shows every manager and on-call engineer the same failed file, owner, and next retry time. With one visible stop, the team can retire three quiet warnings that currently send people to separate logs.
