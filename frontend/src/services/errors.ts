export function apiErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "status" in error) {
    if (error.status === 401)
      return "Your session expired. Sign out and sign in again.";
    if (error.status === 403)
      return "This credential does not have operator access.";
    if (error.status === 404)
      return "The requested incident is no longer available.";
  }
  return "Unable to load data. Check the backend connection and try again.";
}
