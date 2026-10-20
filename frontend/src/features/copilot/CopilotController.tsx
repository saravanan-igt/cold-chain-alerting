"use client";

import { useState } from "react";
import { AiCopilotModal } from "@/components/organisms/AiCopilotModal";
import { apiErrorMessage } from "@/services/errors";
import { useSendAiChatMutation } from "@/services/coldchain-api";
import type { OperationsMessage } from "@/types/domain";

const greeting: OperationsMessage = {
  role: "assistant",
  content:
    "I can summarize the recorded fleet and incident state. I cannot infer equipment failure or determine cargo disposition; follow your approved operating procedure.",
  suggestedActions: ["Summarize open incidents", "Check telemetry freshness"],
};

export function CopilotController({
  open,
  onClose,
  selectedTruckId,
  selectedIncidentId,
}: {
  open: boolean;
  onClose: () => void;
  selectedTruckId?: string;
  selectedIncidentId?: string;
}) {
  const [messages, setMessages] = useState<OperationsMessage[]>([greeting]);
  const [sendChat, { isLoading }] = useSendAiChatMutation();

  const send = async (message: string) => {
    if (!message.trim() || isLoading) return;
    setMessages((current) => [...current, { role: "user", content: message }]);
    try {
      const response = await sendChat({
        message,
        truck_id: selectedTruckId,
        incident_id: selectedIncidentId,
      }).unwrap();
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: response.reply,
          relevantTrucks: response.relevant_trucks,
          suggestedActions: response.suggested_actions,
        },
      ]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        { role: "assistant", content: apiErrorMessage(error) },
      ]);
    }
  };

  return (
    <AiCopilotModal
      open={open}
      onClose={onClose}
      messages={messages}
      isLoading={isLoading}
      onSend={(message) => void send(message)}
    />
  );
}
