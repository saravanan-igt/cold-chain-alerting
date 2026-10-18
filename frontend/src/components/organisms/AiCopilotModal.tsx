"use client";

import React, { useState } from "react";
import Modal from "react-bootstrap/Modal";
import { useSendAiChatMutation } from "@/services/coldchain-api";
import styles from "./AiCopilotModal.module.scss";

interface Message {
  role: "user" | "assistant";
  content: string;
  relevantTrucks?: string[];
  suggestedActions?: string[];
}

interface AiCopilotModalProps {
  open: boolean;
  onClose: () => void;
  selectedTruckId?: string;
  selectedIncidentId?: string;
}

export function AiCopilotModal({
  open,
  onClose,
  selectedTruckId,
  selectedIncidentId,
}: AiCopilotModalProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "Hello! I am Coldline AI, your fleet operations copilot. I can evaluate telemetry trends, explain connectivity gap risks, draft driver messages, and diagnose root causes. How can I help you today?",
      suggestedActions: [
        "Explain T-04 gap risk",
        "Why was T-02 suppressed?",
        "Draft SMS for Driver T-01",
        "Evaluate T-03 sub-threshold drift",
      ],
    },
  ]);
  const [input, setInput] = useState("");
  const [sendChat, { isLoading }] = useSendAiChatMutation();

  const handleSend = async (queryText?: string) => {
    const textToSend = queryText || input;
    if (!textToSend.trim() || isLoading) return;

    const userMsg: Message = { role: "user", content: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");

    try {
      const response = await sendChat({
        message: textToSend,
        truck_id: selectedTruckId,
        incident_id: selectedIncidentId,
      }).unwrap();

      const assistantMsg: Message = {
        role: "assistant",
        content: response.reply,
        relevantTrucks: response.relevant_trucks,
        suggestedActions: response.suggested_actions,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "I encountered a temporary communication error. Please ensure the backend server is running and try again.",
        },
      ]);
    }
  };

  return (
    <Modal show={open} onHide={onClose} size="lg" centered aria-labelledby="copilot-title">
      <Modal.Header closeButton>
        <Modal.Title id="copilot-title">
          Coldline AI · Fleet Operations Copilot
        </Modal.Title>
      </Modal.Header>
      <Modal.Body className={styles.modalBody}>
        <div className={styles.chatHistory}>
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`${styles.messageRow} ${
                m.role === "user" ? styles.user : styles.assistant
              }`}
            >
              <span className={styles.senderLabel}>
                {m.role === "user" ? "You" : "Claude AI Copilot"}
              </span>
              <div className={styles.bubble}>{m.content}</div>

              {m.relevantTrucks && m.relevantTrucks.length > 0 && (
                <div className={styles.relevantTags}>
                  Referenced:
                  {m.relevantTrucks.map((tid) => (
                    <span key={tid}>{tid}</span>
                  ))}
                </div>
              )}

              {m.suggestedActions && m.suggestedActions.length > 0 && (
                <div className={styles.suggestedChips}>
                  {m.suggestedActions.map((action, aIdx) => (
                    <button
                      key={aIdx}
                      type="button"
                      className={styles.chip}
                      onClick={() => handleSend(action)}
                    >
                      {action}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className={`${styles.messageRow} ${styles.assistant}`}>
              <span className={styles.senderLabel}>Claude AI Copilot</span>
              <div className={styles.bubble}>Analyzing fleet telemetry and cold-chain physics...</div>
            </div>
          )}
        </div>

        <form
          className={styles.inputSection}
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
        >
          <input
            type="text"
            className={styles.textInput}
            placeholder="Ask about a truck, incident, gap risk, or draft an SMS..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button
            type="submit"
            className={styles.sendBtn}
            disabled={!input.trim() || isLoading}
          >
            Send
          </button>
        </form>
      </Modal.Body>
    </Modal>
  );
}
