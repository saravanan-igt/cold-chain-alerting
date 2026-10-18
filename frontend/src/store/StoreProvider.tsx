"use client";
import { useEffect, useState, type ReactNode } from "react";
import { Provider } from "react-redux";
import { setupListeners } from "@reduxjs/toolkit/query";
import { disposeStore, makeStore } from "./store";

export function StoreProvider({ children }: { children: ReactNode }) {
  const [store] = useState(() => makeStore());
  useEffect(() => {
    const unsubscribe = setupListeners(store.dispatch);
    return () => {
      unsubscribe();
      disposeStore(store);
    };
  }, [store]);
  return <Provider store={store}>{children}</Provider>;
}
