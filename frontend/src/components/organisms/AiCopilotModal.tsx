"use client";

import React, { useState } from "react";
import Modal from "react-bootstrap/Modal";
import type { OperationsMessage } from "@/types/domain";
import styles from "./AiCopilotModal.module.scss";

interface AiCopilotModalProps {
  open: boolean;
  onClose: () => void;
  messages: OperationsMessage[];
  isLoading: boolean;
  onSend: (message: string) => void;
}

export function AiCopilotModal({
  open,
  onClose,
  messages,
  isLoading,
  onSend,
}: AiCopilotModalProps) {
  const [input, setInput] = useState("");
  const handleSend = (queryText?: string) => {
    const textToSend = (queryText || input).trim();
    if (!textToSend || isLoading) return;
    setInput("");
    onSend(textToSend);
  };

  return (
    <Modal show={open} onHide={onClose} size="lg" centered aria-labelledby="copilot-title">
      <Modal.Header closeButton>
        <Modal.Title id="copilot-title">
          Coldline · Fleet Operations Assistant
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
                {m.role === "user" ? "You" : "Coldline assistant"}
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
              <span className={styles.senderLabel}>Coldline assistant</span>
              <div className={styles.bubble}>Summarizing tenant fleet data...</div>
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
            placeholder="Ask for a summary of current fleet or incident data..."
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
