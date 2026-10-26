export function cropAssessmentKey(name: string): string;
export function dedupeBestAssessmentByCrop<T>(
  items: T[],
  cropNameOf: (item: T) => string,
  statusOf: (item: T) => string | undefined,
): T[];
export function uniqueCropsForAssessment<T extends {
  crop_name: string;
  latitude?: number;
  longitude?: number;
  state?: string;
  district?: string;
}>(crops: T[]): T[];
