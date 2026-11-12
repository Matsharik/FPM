// Короткие имена типов из docs/openapi.json (src/api/schema.d.ts генерирует `npm run gen:types`).
import type { components } from './schema';

type S = components['schemas'];

export type User = S['UserOut'];
export type Me = S['MeOut'];
export type Clock = S['ClockOut'];
export type Overview = S['OverviewOut'];
export type Tile = S['TileOut'];
export type TileKpi = S['TileKpi'];
export type TileRisk = S['TileRisk'];
export type PortfolioSummary = S['PortfolioSummary'];
export type Portfolio = S['PortfolioOut'];
export type NodeDetail = S['NodeDetail'];
export type Contributions = S['ContributionsOut'];
export type Contribution = S['ContributionOut'];
export type AuditOut = S['AuditOut'];
export type AuditRecord = S['AuditRecord'];
export type PeopleOut = S['PeopleOut'];
export type Flag = S['FlagOut'];
export type Trace = S['TraceOut'];
export type TraceStep = S['TraceStep'];
export type KpiSeries = S['KpiSeries'];
export type KpiCard = S['KpiCard'];
export type Graph = S['GraphOut'];
export type GraphNode = S['GraphNode'];
export type GraphLink = S['GraphLink'];
export type GraphKpi = S['GraphKpi'];
export type Deviation = S['DeviationOut'];
export type Advance = S['AdvanceOut'];
export type ResetOut = S['ResetOut'];
export type Source = S['SourceOut'];
export type Glossary = S['GlossaryOut'];
export type Metric = S['MetricOut'];
export type Forecast = S['ForecastOut'];

export type Units = 'natural' | 'relative';
export type KpiStatus = 'green' | 'yellow' | 'red' | 'unknown';
export type DeviationStatus =
  | 'open'
  | 'assigned'
  | 'in_progress'
  | 'done'
  | 'verified'
  | 'failed'
  | 'escalated'
  | 'closed';
export type StageStatus = 'pending' | 'in_progress' | 'done' | 'late' | 'defect';

export type Permission =
  | 'demo.control'
  | 'deviations.manage'
  | 'deviations.recheck'
  | 'deviations.done'
  | 'flags.write'
  | 'people.read'
  | 'points.write'
  | 'structure.write'
  | 'glossary.write'
  | 'config.io';
