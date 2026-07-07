The migration project began on a rainy Saturday. I wanted to move the old database to new hardware over one weekend.

The schema felt stable from the start, a solid base for the cutover.

The export ran for two hours and streamed the rows to disk.

The import needed three passes to finish, and I retried between each failure.

One rollback script saved the cutover by catching the last error.

The migration project is done, and that one weekend of database work and cloud credit was worth the $40.
