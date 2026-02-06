# Rule Engine

The rule engine is deterministic and explainable. It inspects parsed SQL and execution plans to generate findings with evidence. It does not guess or infer beyond observed facts.

## Severity Scale
- **S1**: Low impact or best-practice guidance
- **S2**: Likely performance impact
- **S3**: High impact or urgent issue

## SQL Structure Rules
- **Avoid SELECT \***: reduces IO and improves index-only scan potential
- **Missing WHERE**: full-table scans are likely
- **ORDER BY without LIMIT**: can force expensive full sorts
- **Functions in WHERE**: can block index usage

## Plan-Based Rules
- **Sequential scan with filter**: suggest index on filtered columns
- **Sequential scan without filter**: suggest adding filters or limits
- **Large sort**: suggest index on sort key or reduce rows
- **Nested loop with large rows**: suggest join index or join strategy
- **Hash spill**: suggest increasing `work_mem` or reducing input
- **Many rows removed by filter**: suggest more selective predicate or index
- **Row estimate mismatch**: suggest `ANALYZE` to refresh stats

## Optimization Score
The UI shows a simple score out of 100.
- Severity 1 issues reduce the score a little.
- Severity 2 issues reduce the score more.
- Severity 3 issues reduce the score the most.

## Index Recommendations
Index candidates are generated from:
- Columns used in filters (WHERE)
- Columns used in join conditions (ON)

## Extending the Rules
Add new rules in `backend/app/rules.py`. Each rule should:
- Include evidence from SQL or plan fields
- Produce a specific, explainable recommendation
- Avoid guessing about data not present in the plan
