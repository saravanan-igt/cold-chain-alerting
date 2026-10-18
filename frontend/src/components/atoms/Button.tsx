"use client";
import BootstrapButton, { type ButtonProps } from "react-bootstrap/Button";

/** Product button boundary; consumers do not depend directly on the UI vendor. */
export function Button(props: Omit<ButtonProps, "as">) {
  return <BootstrapButton {...props} />;
}
