export {
  SITE_TOTAL_DIMENSION,
  AVG_METRICS,
  PAID_SOURCES,
  filterMetricsByDimension,
  getUniqueDimensionValues,
  linearRegression,
  generateProjection,
  buildPageMetrics,
  filterSiteMetrics,
  seriesByDate,
} from "./series";

export { buildKpiSummaries, formatKpiValue, KPI_DEFAULTS } from "./kpi";

export type { PeriodOption, KpiSummary, KpiTarget } from "./kpi";

export { insightKind, gradeFromScore, areasFromBackendPillars, buildHealthFromApi } from "./health";

export type {
  HealthArea,
  ClientHealth,
  HealthGrade,
  HealthImprovement,
  BackendPillars,
  ApiHealthInput,
} from "./health";
