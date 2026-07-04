Picking an ORM strategy depends on what your team already knows and how much SQL you want to see in code review, which is a fuzzier question than any benchmark can settle. We compared the three approaches on the same schema. The results surprised us.

In Rails, the association preloads three tables with a single call and the query log stays readable. In Django, the same join requires an explicit select_related chain that new hires reliably forget until the page times out. In raw SQL, you write nine lines by hand.

So the "slow" option won. Latency under load dropped by a third once we moved the two hottest paths to handwritten queries, while the framework defaults quietly traded speed for a convenience nobody on the team had actually asked for. We let the ORM keep everything else. Nobody has touched those nine lines since March.
