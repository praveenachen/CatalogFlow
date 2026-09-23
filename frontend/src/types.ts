export type ViewId = 'overview' | 'batches' | 'schema' | 'records' | 'review' | 'publish'
export type MappingMethod = 'exact' | 'alias' | 'fuzzy' | 'unresolved'
export type AutomationStatus = 'Auto-approved' | 'Needs Review' | 'Duplicate' | 'Invalid'
export type ReviewStatus = 'pending' | 'not_required' | 'approved' | 'edited' | 'rejected'
export type ProcessingStatus = 'PENDING' | 'SUBMITTED' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'pending' | 'submitted' | 'running' | 'completed' | 'failed' | 'cancelled'
export type ProcessorType = 'local' | 'databricks'

export type ColumnProfile = {
  source_name: string
  inferred_type: string
  null_percentage: number
  unique_percentage: number
  sample_values: string[]
  validity_rate?: number | null
}

export type Mapping = {
  source_field: string
  canonical_field?: string | null
  method: MappingMethod
  confidence: number
  auto_applied: boolean
}

export type SchemaReport = {
  missing_columns: string[]
  unexpected_columns: string[]
  suggested_mappings: Record<string, string>
  auto_applied_mappings: Record<string, string>
  unresolved_mappings: Record<string, string>
  drift_severity: string
  profiles: ColumnProfile[]
}

export type BatchSummary = {
  upload_id: number
  batch_id: number
  filename: string
  uploaded_at: string
  total_records: number
  auto_approved_count: number
  needs_review_count: number
  duplicate_count: number
  invalid_count: number
  attention_count: number
  publishable_count: number
  average_confidence: number
  schema_drift_detected: boolean
  schema_drift_count: number
  schema_drift_severity: string
  default_currency?: string | null
  quality_metrics: Record<string, unknown>
  status: ProcessingStatus
  run_id?: number | null
  processor_type?: ProcessorType | null
  processing_status?: ProcessingStatus | null
  external_run_id?: string | null
  raw_uri?: string | null
  processed_uri?: string | null
  curated_uri?: string | null
  schema_report: SchemaReport
  mappings: Mapping[]
}

export type QualityComponent = {
  score: number
  weight: number
  reasons: string[]
}

export type NormalizationTrace = {
  field: string
  original_value?: unknown
  normalized_value?: unknown
  rule: string
  certainty: number
}

export type RecordItem = {
  id: number
  batch_id: number
  sku?: string | null
  original_product_name?: string | null
  original_category?: string | null
  original_price?: string | null
  original_inventory?: string | null
  original_tags?: string | null
  cleaned_product_name?: string | null
  cleaned_description?: string | null
  cleaned_category?: string | null
  cleaned_price?: number | null
  cleaned_currency?: string | null
  cleaned_inventory?: number | null
  cleaned_tags?: string | null
  confidence_score: number
  automation_confidence: number
  quality_components: Record<string, QualityComponent>
  normalization_trace: NormalizationTrace[]
  status: AutomationStatus
  recommended_action: string
  issue_reasons: string[]
  severity: string
  review_status: ReviewStatus
  reviewed_at?: string | null
  reviewer_decision?: ReviewDecision | null
  reviewed: boolean
  exportable: boolean
  duplicate_of_record_id?: number | null
  duplicate_method?: string | null
  duplicate_confidence?: number | null
}

export type ProcessingRun = {
  id: number
  batch_id: number
  processor_type: ProcessorType
  external_run_id?: string | null
  status: ProcessingStatus
  started_at: string
  completed_at?: string | null
  error_code?: string | null
  error_message?: string | null
  raw_uri?: string | null
  processed_uri?: string | null
  curated_uri?: string | null
  result_metadata: Record<string, unknown>
}

export type ReviewDecision = 'approved' | 'edited' | 'rejected'

export type ReviewPatch = {
  cleaned_product_name?: string
  cleaned_description?: string
  cleaned_category?: string
  cleaned_price?: number
  cleaned_currency?: string
  cleaned_inventory?: number
  cleaned_tags?: string
  decision: ReviewDecision
}
