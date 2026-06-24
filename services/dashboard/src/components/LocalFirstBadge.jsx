import React from "react";
import { pillBadge } from "../theme.js";
import { LockIcon } from "./Icons.jsx";

export default function LocalFirstBadge({ style }) {
  return (
    <span style={{ ...pillBadge, ...style }}>
      <LockIcon width={13} height={13} />
      100% on-device · no network
    </span>
  );
}
