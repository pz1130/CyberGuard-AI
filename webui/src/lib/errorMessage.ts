/** Safe string from a `catch (e: unknown)` value. */
export function errorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message
  if (typeof err === 'string' && err) return err
  return String(err)
}
