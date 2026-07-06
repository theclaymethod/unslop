# Import Reliability Review

The nightly import failed six times in May. Four failures came from duplicate vendor rows, one came from a malformed date, and one came from a timeout while the warehouse file was still uploading. Analysts predict the timeout rate will fall after the storage move, but the report does not name a source for that forecast.

The current parser accepts the first vendor row and logs the rest as warnings, highlighting the cleanup issue without stopping the job. That behavior made the dashboard look current even when the warehouse team still needed the rejected rows. Not more alerts. Better stops.

The proposed fix is a preflight check that blocks duplicate vendor IDs before the import writes any rows. Whether you're a manager or an on-call engineer, the status page should show the same failed file, owner, and next retry time. In conclusion, the import needs one visible stop rather than three quiet warnings.
