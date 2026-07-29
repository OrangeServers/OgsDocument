import type {
  AiApiResponse,
  AiDiagnosticEvidence,
  AiDiagnosticProfile,
  AiDiagnosticReport,
  AiDiagnosticRun,
  AiDiagnosticStartRequest,
} from '@/types/ai'
import { aiJsonRequest } from '@/utils/aiStream'

type ProfilesEnvelope = AiApiResponse<AiDiagnosticProfile[]> & {
  profiles?: AiDiagnosticProfile[]
}

type RunEnvelope = AiApiResponse<AiDiagnosticRun> & {
  run?: AiDiagnosticRun
  diagnostic?: AiDiagnosticRun
}

type EvidenceEnvelope = AiApiResponse<AiDiagnosticEvidence[]> & {
  evidence?: AiDiagnosticEvidence[]
  items?: AiDiagnosticEvidence[]
}

type ReportEnvelope = AiApiResponse<AiDiagnosticReport> & {
  report?: AiDiagnosticReport
}

function objectData<T extends object>(
  payload: AiApiResponse<T> & Record<string, unknown>,
  ...keys: string[]
): T {
  for (const key of keys) {
    const value = payload[key]
    if (value && typeof value === 'object' && !Array.isArray(value)) return value as T
  }
  if (payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)) {
    const data = payload.data as Record<string, unknown>
    for (const key of keys) {
      const value = data[key]
      if (value && typeof value === 'object' && !Array.isArray(value)) return value as T
    }
    return data as T
  }
  return payload as T
}

function arrayData<T>(
  payload: AiApiResponse<T[]> & Record<string, unknown>,
  ...keys: string[]
): T[] {
  for (const key of keys) {
    const value = payload[key]
    if (Array.isArray(value)) return value as T[]
  }
  if (Array.isArray(payload.data)) return payload.data
  if (payload.data && typeof payload.data === 'object') {
    for (const key of keys) {
      const value = (payload.data as Record<string, unknown>)[key]
      if (Array.isArray(value)) return value as T[]
    }
  }
  return []
}

export async function getDiagnosticProfiles(): Promise<AiDiagnosticProfile[]> {
  const payload = await aiJsonRequest<ProfilesEnvelope>('/ai/diagnostic-profiles')
  return arrayData(payload, 'profiles')
}

export async function startDiagnostic(
  request: AiDiagnosticStartRequest,
): Promise<AiDiagnosticRun> {
  const payload = await aiJsonRequest<RunEnvelope>('/ai/diagnostics', {
    method: 'POST',
    body: request as unknown as Record<string, unknown>,
  })
  return objectData(payload, 'run', 'diagnostic')
}

export async function getDiagnosticRun(runId: string): Promise<AiDiagnosticRun> {
  const payload = await aiJsonRequest<RunEnvelope>(
    `/ai/diagnostics/${encodeURIComponent(runId)}`,
  )
  return objectData(payload, 'run', 'diagnostic')
}

export async function cancelDiagnostic(runId: string): Promise<AiDiagnosticRun> {
  const payload = await aiJsonRequest<RunEnvelope>(
    `/ai/diagnostics/${encodeURIComponent(runId)}/cancel`,
    { method: 'POST', body: {} },
  )
  return objectData(payload, 'run', 'diagnostic')
}

export async function getDiagnosticEvidence(
  runId: string,
): Promise<AiDiagnosticEvidence[]> {
  const payload = await aiJsonRequest<EvidenceEnvelope>(
    `/ai/diagnostics/${encodeURIComponent(runId)}/evidence`,
  )
  return arrayData(payload, 'evidence', 'items')
}

export async function getDiagnosticReport(runId: string): Promise<AiDiagnosticReport> {
  const payload = await aiJsonRequest<ReportEnvelope>(
    `/ai/diagnostics/${encodeURIComponent(runId)}/report`,
  )
  return objectData(payload, 'report')
}
