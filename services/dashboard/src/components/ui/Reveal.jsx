import React, { useEffect, useRef, useState } from "react";

// Scroll-in reveal. Adds the `is-visible` class (see index.css `.ts-reveal`) once the
// element enters the viewport. No dependency — uses IntersectionObserver. `delay` staggers
// siblings; `as` lets it wrap any tag.
export default function Reveal({ children, delay = 0, as: Tag = "div", style, className = "", once = true, ...rest }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setVisible(true);
            if (once) io.unobserve(e.target);
          } else if (!once) {
            setVisible(false);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [once]);

  return (
    <Tag
      ref={ref}
      className={`ts-reveal ${visible ? "is-visible" : ""} ${className}`}
      style={{ animationDelay: visible ? `${delay}ms` : undefined, ...style }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
