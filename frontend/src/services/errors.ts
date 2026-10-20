export function apiErrorMessage(error: unknown): string {
  if (error && typeof error === "object" && "status" in error) {
    if (error.status === 401)
      return "Your session expired. Sign out and sign in again.";
    if (error.status === 403)
      return "This credential does not have operator access.";
    if (error.status === 404)
      return "The requested incident is no longer available.";
    // Conflicts and validation failures carry an actionable, non-sensitive server message.
    if (
      (error.status === 409 || error.status === 422) &&
      "data" in error &&
      error.data &&
      typeof error.data === "object" &&
      "detail" in error.data &&
      typeof error.data.detail === "string"
    )
      return error.data.detail;
  }
  return "Unable to load data. Check the backend connection and try again.";
}
