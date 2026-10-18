import Alert from "react-bootstrap/Alert";
import { Button } from "@/components/atoms/Button";
export function QueryFeedback({
  loading,
  error,
  onRetry,
}: {
  loading: boolean;
  error?: string;
  onRetry: () => void;
}) {
  if (error)
    return (
      <Alert variant="danger" role="alert">
        {error} Previously loaded data may be outdated.
        <Button
          variant="outline-danger"
          size="sm"
          className="ms-3"
          onClick={onRetry}
        >
          Retry
        </Button>
      </Alert>
    );
  return loading ? (
    <p className="p-3" role="status">
      Loading data…
    </p>
  ) : null;
}
