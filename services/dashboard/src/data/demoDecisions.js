// AUTO-CAPTURED from the live risk backend (POST /risk/demo/score/{id}).
// Baked-in so the Investigator renders the curated cases with the backend DOWN.
// Overlay images live under public/demo/ (referenced by path, not inlined).
export const DEMO_DECISIONS = {
  "PKT-0001": {
    "decision": {
      "packet_id": "PKT-0001",
      "trust_score": {
        "overall": 98.7,
        "forensic_subscore": 100.0,
        "semantic_subscore": 100.0,
        "anomaly_subscore": 100.0,
        "version": "4.0.0",
        "computed_at": "2026-06-24T01:35:36.392487Z"
      },
      "evidence_chain": [
        {
          "id": "ev_818b98a1774a",
          "category": "graph",
          "severity": "info",
          "title": "Repeat applicant",
          "description": "The same applicant appears in 2 other application(s): PKT-0009, PKT-0017. Provided for context; not fraud on its own.",
          "source_doc_id": null,
          "source_location": "cross-application graph",
          "values": {
            "other_applications": [
              "PKT-0009",
              "PKT-0017"
            ]
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:36.384648Z"
        },
        {
          "id": "ev_a9930c20a26b",
          "category": "anomaly",
          "severity": "info",
          "title": "Learned risk model assessment",
          "description": "The trained risk model assigns this packet a fraud probability of 0%. Leading factors: submission timing relative to document creation; spread of document creation dates.",
          "source_doc_id": null,
          "source_location": "risk model (gradient-boosted trees + isolation forest)",
          "values": {
            "fraud_probability": 0.0,
            "anomaly_score": 0.261,
            "top_factors": [
              {
                "factor": "submission timing relative to document creation",
                "weight": 0.8996
              },
              {
                "factor": "spread of document creation dates",
                "weight": 0.1004
              }
            ],
            "model_version": "4.0.0"
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:36.392466Z"
        }
      ],
      "recommendation": {
        "action": "approve",
        "rationale": "Trust score 99/100 is at or above the approval threshold (70); no tampering or inconsistency of concern.",
        "thresholds_used": {
          "approve_at_or_above": 70.0,
          "freeze_below": 40.0,
          "critical_trust_ceiling": 25.0,
          "weights": {
            "model": 0.55,
            "forensic": 0.25,
            "semantic": 0.15,
            "anomaly": 0.05
          }
        }
      }
    },
    "subgraph": {
      "nodes": [
        {
          "id": "employer:Infosys Limited",
          "kind": "employer",
          "label": "Infosys Limited"
        },
        {
          "id": "pan:ABMPS1234F",
          "kind": "pan",
          "label": "ABMPS1234F"
        },
        {
          "id": "app:PKT-0001",
          "kind": "app",
          "label": "PKT-0001"
        },
        {
          "id": "app:PKT-0017",
          "kind": "app",
          "label": "PKT-0017"
        },
        {
          "id": "app:PKT-0009",
          "kind": "app",
          "label": "PKT-0009"
        }
      ],
      "edges": [
        {
          "source": "app:PKT-0001",
          "target": "pan:ABMPS1234F"
        },
        {
          "source": "app:PKT-0001",
          "target": "employer:Infosys Limited"
        },
        {
          "source": "pan:ABMPS1234F",
          "target": "app:PKT-0009"
        },
        {
          "source": "pan:ABMPS1234F",
          "target": "app:PKT-0017"
        },
        {
          "source": "employer:Infosys Limited",
          "target": "app:PKT-0009"
        },
        {
          "source": "employer:Infosys Limited",
          "target": "app:PKT-0017"
        }
      ]
    },
    "overlays": []
  },
  "PKT-0010": {
    "decision": {
      "packet_id": "PKT-0010",
      "trust_score": {
        "overall": 26.2,
        "forensic_subscore": 30.0,
        "semantic_subscore": 100.0,
        "anomaly_subscore": 0.0,
        "version": "4.0.0",
        "computed_at": "2026-06-24T01:35:39.037735Z"
      },
      "evidence_chain": [
        {
          "id": "ev_4a4525fafb7e",
          "category": "anomaly",
          "severity": "high",
          "title": "Learned risk model assessment",
          "description": "The trained risk model assigns this packet a fraud probability of 100%. Leading factors: submission timing relative to document creation; spread of document creation dates; number of document tamper signals.",
          "source_doc_id": null,
          "source_location": "risk model (gradient-boosted trees + isolation forest)",
          "values": {
            "fraud_probability": 1.0,
            "anomaly_score": 0.261,
            "top_factors": [
              {
                "factor": "submission timing relative to document creation",
                "weight": 0.9569
              },
              {
                "factor": "spread of document creation dates",
                "weight": 0.0178
              },
              {
                "factor": "number of document tamper signals",
                "weight": 0.0177
              }
            ],
            "model_version": "4.0.0"
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:39.037713Z"
        },
        {
          "id": "ev_09479c0595fb",
          "category": "forensic",
          "severity": "high",
          "title": "White-box edit detected (covered text)",
          "description": "'form16.pdf' page 1 contains 1 white-filled rectangle(s) drawn over existing text content. This is a classic 'whiteout' technique: the original value is hidden visually but survives in the PDF content stream.",
          "source_doc_id": null,
          "source_location": "page 1 â€” drawing objects vs text layer",
          "values": {
            "page": 1,
            "whitebox_count": 1,
            "regions": [
              {
                "page": 1,
                "bbox": [
                  318.0,
                  233.1,
                  424.7,
                  253.6
                ]
              }
            ]
          },
          "confidence": 0.88,
          "created_at": "2026-06-24T01:35:36.903639Z"
        },
        {
          "id": "ev_83b7b03cb209",
          "category": "forensic",
          "severity": "high",
          "title": "Visible content contradicts PDF text layer (re-OCR cross-check)",
          "description": "'form16.pdf' page 1: the monetary amount '1,450,000' is present in the PDF text layer but is not visible on the rendered page â€” a hallmark of a covered/overlaid edit where the original survives in the content stream while a different value (or none) is shown. This check reads pixels (OCR), not PDF structure, so it catches edits even when structural residue is cleaned or the document is flattened.",
          "source_doc_id": null,
          "source_location": "page 1 â€” rendered image vs text layer",
          "values": {
            "page": 1,
            "check": "reocr",
            "kind": "money",
            "hidden_text_layer_value": "1,450,000",
            "visible_values": [
              "145,000",
              "2,755,000"
            ],
            "regions": [
              {
                "page": 1,
                "bbox": [
                  341.3,
                  235.1,
                  394.7,
                  251.6
                ]
              }
            ]
          },
          "confidence": 0.85,
          "created_at": "2026-06-24T01:35:37.178236Z"
        },
        {
          "id": "ev_a2690817a959",
          "category": "graph",
          "severity": "info",
          "title": "Repeat applicant",
          "description": "The same applicant appears in 2 other application(s): PKT-0002, PKT-0025. Provided for context; not fraud on its own.",
          "source_doc_id": null,
          "source_location": "cross-application graph",
          "values": {
            "other_applications": [
              "PKT-0002",
              "PKT-0025"
            ]
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:39.030550Z"
        }
      ],
      "recommendation": {
        "action": "freeze",
        "rationale": "Trust score 26/100 is below the freeze threshold (40) and is backed by concrete document-level evidence (forensic and/or semantic findings). Recommend freezing pending investigation.",
        "thresholds_used": {
          "approve_at_or_above": 70.0,
          "freeze_below": 40.0,
          "critical_trust_ceiling": 25.0,
          "weights": {
            "model": 0.55,
            "forensic": 0.25,
            "semantic": 0.15,
            "anomaly": 0.05
          }
        }
      }
    },
    "subgraph": {
      "nodes": [
        {
          "id": "employer:Tata Consultancy Services",
          "kind": "employer",
          "label": "Tata Consultancy Services"
        },
        {
          "id": "app:PKT-0025",
          "kind": "app",
          "label": "PKT-0025"
        },
        {
          "id": "app:PKT-0028",
          "kind": "app",
          "label": "PKT-0028"
        },
        {
          "id": "template:6785e85709f53a1157c200b0abad584d",
          "kind": "template",
          "label": "6785e85709f53a1157c200b0abad584d"
        },
        {
          "id": "app:PKT-0002",
          "kind": "app",
          "label": "PKT-0002"
        },
        {
          "id": "app:PKT-0010",
          "kind": "app",
          "label": "PKT-0010"
        },
        {
          "id": "pan:CDNPV5678L",
          "kind": "pan",
          "label": "CDNPV5678L"
        },
        {
          "id": "app:PKT-0027",
          "kind": "app",
          "label": "PKT-0027"
        }
      ],
      "edges": [
        {
          "source": "app:PKT-0002",
          "target": "pan:CDNPV5678L"
        },
        {
          "source": "app:PKT-0002",
          "target": "employer:Tata Consultancy Services"
        },
        {
          "source": "pan:CDNPV5678L",
          "target": "app:PKT-0010"
        },
        {
          "source": "pan:CDNPV5678L",
          "target": "app:PKT-0025"
        },
        {
          "source": "employer:Tata Consultancy Services",
          "target": "app:PKT-0010"
        },
        {
          "source": "employer:Tata Consultancy Services",
          "target": "app:PKT-0025"
        },
        {
          "source": "app:PKT-0010",
          "target": "template:6785e85709f53a1157c200b0abad584d"
        },
        {
          "source": "template:6785e85709f53a1157c200b0abad584d",
          "target": "app:PKT-0027"
        },
        {
          "source": "template:6785e85709f53a1157c200b0abad584d",
          "target": "app:PKT-0028"
        }
      ]
    },
    "overlays": [
      {
        "doc": "form16.pdf",
        "page": 1,
        "src": "demo/PKT-0010_0.png"
      }
    ]
  },
  "PKT-0028": {
    "decision": {
      "packet_id": "PKT-0028",
      "trust_score": {
        "overall": 7.4,
        "forensic_subscore": 30.0,
        "semantic_subscore": 40.0,
        "anomaly_subscore": 0.0,
        "version": "4.0.0",
        "computed_at": "2026-06-24T01:35:43.660340Z"
      },
      "evidence_chain": [
        {
          "id": "ev_fcd1d0d86d96",
          "category": "semantic",
          "severity": "critical",
          "title": "Encumbrance certificate contradicts CERSAI registry",
          "description": "The encumbrance certificate for property SY-058/1A claims no encumbrances, but the CERSAI registry records 1 active charge(s) under PAN GHJPR3456M: HDFC Bank Rs. 4,200,000 (registered 2021-11-04). An undisclosed mortgage is a serious underwriting risk.",
          "source_doc_id": null,
          "source_location": "encumbrance_certificate.pdf vs CERSAI registry",
          "values": {
            "property_id": "SY-058/1A",
            "applicant_pan": "GHJPR3456M",
            "cersai_charges": [
              {
                "property_id": "SY-058/1A",
                "asset_type": "residential_property",
                "lender": "HDFC Bank",
                "amount": 4200000,
                "registered_on": "2021-11-04",
                "status": "active"
              }
            ],
            "ec_claims_nil": true
          },
          "confidence": 0.95,
          "created_at": "2026-06-24T01:35:42.275640Z"
        },
        {
          "id": "ev_4fe49a9a81d9",
          "category": "anomaly",
          "severity": "high",
          "title": "Learned risk model assessment",
          "description": "The trained risk model assigns this packet a fraud probability of 100%. Leading factors: submission timing relative to document creation; number of cross-document inconsistencies; spread of document creation dates; number of document tamper signals.",
          "source_doc_id": null,
          "source_location": "risk model (gradient-boosted trees + isolation forest)",
          "values": {
            "fraud_probability": 1.0,
            "anomaly_score": 0.4148,
            "top_factors": [
              {
                "factor": "submission timing relative to document creation",
                "weight": 0.8006
              },
              {
                "factor": "number of cross-document inconsistencies",
                "weight": 0.1187
              },
              {
                "factor": "spread of document creation dates",
                "weight": 0.0595
              },
              {
                "factor": "number of document tamper signals",
                "weight": 0.0148
              }
            ],
            "model_version": "4.0.0"
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:43.660319Z"
        },
        {
          "id": "ev_d5b7a3d55607",
          "category": "forensic",
          "severity": "high",
          "title": "White-box edit detected (covered text)",
          "description": "'encumbrance_certificate.pdf' page 1 contains 1 white-filled rectangle(s) drawn over existing text content. This is a classic 'whiteout' technique: the original value is hidden visually but survives in the PDF content stream.",
          "source_doc_id": null,
          "source_location": "page 1 â€” drawing objects vs text layer",
          "values": {
            "page": 1,
            "whitebox_count": 1,
            "regions": [
              {
                "page": 1,
                "bbox": [
                  177.8,
                  202.2,
                  535.0,
                  221.3
                ]
              }
            ]
          },
          "confidence": 0.88,
          "created_at": "2026-06-24T01:35:40.989422Z"
        },
        {
          "id": "ev_8a747500e76c",
          "category": "forensic",
          "severity": "high",
          "title": "Visible content contradicts PDF text layer (re-OCR cross-check)",
          "description": "'encumbrance_certificate.pdf' page 1: the monetary amount '4,200,000' is present in the PDF text layer but is not visible on the rendered page â€” a hallmark of a covered/overlaid edit where the original survives in the content stream while a different value (or none) is shown. This check reads pixels (OCR), not PDF structure, so it catches edits even when structural residue is cleaned or the document is flattened.",
          "source_doc_id": null,
          "source_location": "page 1 â€” rendered image vs text layer",
          "values": {
            "page": 1,
            "check": "reocr",
            "kind": "money",
            "hidden_text_layer_value": "4,200,000",
            "visible_values": [],
            "regions": [
              {
                "page": 1,
                "bbox": [
                  264.2,
                  204.2,
                  313.1,
                  219.3
                ]
              }
            ]
          },
          "confidence": 0.85,
          "created_at": "2026-06-24T01:35:41.288070Z"
        },
        {
          "id": "ev_bfa9727709d0",
          "category": "graph",
          "severity": "medium",
          "title": "Collateral pledged across multiple applications",
          "description": "Property SY-058/1A is pledged as collateral in 1 other live application(s) by 2 distinct applicants (PKT-0026). This is the signature of double-financing / loan stacking â€” the same asset financed more than once.",
          "source_doc_id": null,
          "source_location": "cross-application graph",
          "values": {
            "property_id": "SY-058/1A",
            "other_applications": [
              "PKT-0026"
            ],
            "distinct_applicants": 2
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:43.653120Z"
        },
        {
          "id": "ev_ae1ced1e6746",
          "category": "graph",
          "severity": "info",
          "title": "Repeat applicant",
          "description": "The same applicant appears in 2 other application(s): PKT-0004, PKT-0012. Provided for context; not fraud on its own.",
          "source_doc_id": null,
          "source_location": "cross-application graph",
          "values": {
            "other_applications": [
              "PKT-0004",
              "PKT-0012"
            ]
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:43.653154Z"
        }
      ],
      "recommendation": {
        "action": "freeze",
        "rationale": "Trust score 7/100 is below the freeze threshold (40) and is backed by concrete document-level evidence (forensic and/or semantic findings). Recommend freezing pending investigation.",
        "thresholds_used": {
          "approve_at_or_above": 70.0,
          "freeze_below": 40.0,
          "critical_trust_ceiling": 25.0,
          "weights": {
            "model": 0.55,
            "forensic": 0.25,
            "semantic": 0.15,
            "anomaly": 0.05
          }
        }
      }
    },
    "subgraph": {
      "nodes": [
        {
          "id": "app:PKT-0028",
          "kind": "app",
          "label": "PKT-0028"
        },
        {
          "id": "app:PKT-0012",
          "kind": "app",
          "label": "PKT-0012"
        },
        {
          "id": "pan:GHJPR3456M",
          "kind": "pan",
          "label": "GHJPR3456M"
        },
        {
          "id": "template:6785e85709f53a1157c200b0abad584d",
          "kind": "template",
          "label": "6785e85709f53a1157c200b0abad584d"
        },
        {
          "id": "app:PKT-0026",
          "kind": "app",
          "label": "PKT-0026"
        },
        {
          "id": "app:PKT-0010",
          "kind": "app",
          "label": "PKT-0010"
        },
        {
          "id": "app:PKT-0004",
          "kind": "app",
          "label": "PKT-0004"
        },
        {
          "id": "employer:HDFC Bank",
          "kind": "employer",
          "label": "HDFC Bank"
        },
        {
          "id": "app:PKT-0027",
          "kind": "app",
          "label": "PKT-0027"
        },
        {
          "id": "property:SY-058/1A",
          "kind": "property",
          "label": "SY-058/1A"
        }
      ],
      "edges": [
        {
          "source": "app:PKT-0004",
          "target": "pan:GHJPR3456M"
        },
        {
          "source": "app:PKT-0004",
          "target": "employer:HDFC Bank"
        },
        {
          "source": "pan:GHJPR3456M",
          "target": "app:PKT-0012"
        },
        {
          "source": "pan:GHJPR3456M",
          "target": "app:PKT-0028"
        },
        {
          "source": "employer:HDFC Bank",
          "target": "app:PKT-0012"
        },
        {
          "source": "employer:HDFC Bank",
          "target": "app:PKT-0028"
        },
        {
          "source": "app:PKT-0010",
          "target": "template:6785e85709f53a1157c200b0abad584d"
        },
        {
          "source": "template:6785e85709f53a1157c200b0abad584d",
          "target": "app:PKT-0027"
        },
        {
          "source": "template:6785e85709f53a1157c200b0abad584d",
          "target": "app:PKT-0028"
        },
        {
          "source": "app:PKT-0026",
          "target": "property:SY-058/1A"
        },
        {
          "source": "property:SY-058/1A",
          "target": "app:PKT-0028"
        }
      ]
    },
    "overlays": [
      {
        "doc": "encumbrance_certificate.pdf",
        "page": 1,
        "src": "demo/PKT-0028_0.png"
      }
    ]
  },
  "PKT-0031": {
    "decision": {
      "packet_id": "PKT-0031",
      "trust_score": {
        "overall": 12.9,
        "forensic_subscore": 100.0,
        "semantic_subscore": 100.0,
        "anomaly_subscore": 0.0,
        "version": "4.0.0",
        "computed_at": "2026-06-24T01:35:48.112915Z"
      },
      "evidence_chain": [
        {
          "id": "ev_98199cb99129",
          "category": "graph",
          "severity": "critical",
          "title": "Collateral pledged across multiple applications",
          "description": "Property SY-911/2C is pledged as collateral in 3 other live application(s) by 4 distinct applicants (PKT-0029, PKT-0032, PKT-0033). This is the signature of double-financing / loan stacking â€” the same asset financed more than once.",
          "source_doc_id": null,
          "source_location": "cross-application graph",
          "values": {
            "property_id": "SY-911/2C",
            "other_applications": [
              "PKT-0029",
              "PKT-0032",
              "PKT-0033"
            ],
            "distinct_applicants": 4
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:48.102707Z"
        },
        {
          "id": "ev_0e4ba3a013f7",
          "category": "anomaly",
          "severity": "high",
          "title": "Learned risk model assessment",
          "description": "The trained risk model assigns this packet a fraud probability of 100%. Leading factors: submission timing relative to document creation; spread of document creation dates.",
          "source_doc_id": null,
          "source_location": "risk model (gradient-boosted trees + isolation forest)",
          "values": {
            "fraud_probability": 1.0,
            "anomaly_score": 0.4148,
            "top_factors": [
              {
                "factor": "submission timing relative to document creation",
                "weight": 0.961
              },
              {
                "factor": "spread of document creation dates",
                "weight": 0.039
              }
            ],
            "model_version": "4.0.0"
          },
          "confidence": 1.0,
          "created_at": "2026-06-24T01:35:48.112886Z"
        }
      ],
      "recommendation": {
        "action": "freeze",
        "rationale": "Trust score 13/100 is below the freeze threshold (40) and is backed by concrete document-level evidence (forensic and/or semantic findings). Recommend freezing pending investigation.",
        "thresholds_used": {
          "approve_at_or_above": 70.0,
          "freeze_below": 40.0,
          "critical_trust_ceiling": 25.0,
          "weights": {
            "model": 0.55,
            "forensic": 0.25,
            "semantic": 0.15,
            "anomaly": 0.05
          }
        }
      }
    },
    "subgraph": {
      "nodes": [
        {
          "id": "employer:Shaikh Trading Co",
          "kind": "employer",
          "label": "Shaikh Trading Co"
        },
        {
          "id": "app:PKT-0032",
          "kind": "app",
          "label": "PKT-0032"
        },
        {
          "id": "property:SY-911/2C",
          "kind": "property",
          "label": "SY-911/2C"
        },
        {
          "id": "app:PKT-0031",
          "kind": "app",
          "label": "PKT-0031"
        },
        {
          "id": "pan:ZZEPS5555E",
          "kind": "pan",
          "label": "ZZEPS5555E"
        },
        {
          "id": "app:PKT-0033",
          "kind": "app",
          "label": "PKT-0033"
        },
        {
          "id": "app:PKT-0029",
          "kind": "app",
          "label": "PKT-0029"
        }
      ],
      "edges": [
        {
          "source": "app:PKT-0029",
          "target": "property:SY-911/2C"
        },
        {
          "source": "property:SY-911/2C",
          "target": "app:PKT-0031"
        },
        {
          "source": "property:SY-911/2C",
          "target": "app:PKT-0032"
        },
        {
          "source": "property:SY-911/2C",
          "target": "app:PKT-0033"
        },
        {
          "source": "app:PKT-0031",
          "target": "pan:ZZEPS5555E"
        },
        {
          "source": "app:PKT-0031",
          "target": "employer:Shaikh Trading Co"
        }
      ]
    },
    "overlays": []
  }
};
