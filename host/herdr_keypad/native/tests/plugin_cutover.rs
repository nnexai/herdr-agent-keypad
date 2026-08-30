use std::collections::BTreeSet;

const LIFECYCLE: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/../LIFECYCLE.md"));

fn section_body(document: &str, heading: &str) -> String {
    let start = document
        .find(heading)
        .unwrap_or_else(|| panic!("missing required heading {heading:?}"));
    let body_start = start + heading.len();
    let rest = &document[body_start..];
    let end = rest.find("\n## ").unwrap_or(rest.len());
    rest[..end].to_owned()
}

fn numbered_steps(body: &str) -> Vec<String> {
    body.lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            let (number, step) = trimmed.split_once(". ")?;
            if number.chars().all(|character| character.is_ascii_digit()) {
                Some(step.to_owned())
            } else {
                None
            }
        })
        .collect()
}

fn assert_ordered(document: &str, terms: &[&str]) {
    let mut previous = 0;
    for term in terms {
        let position = document
            .find(term)
            .unwrap_or_else(|| panic!("missing required normative term {term:?}"));
        assert!(position >= previous, "term {term:?} is out of order");
        previous = position;
    }
}

#[test]
fn lifecycle_document_has_ordered_required_sections() {
    let headings = [
        "## Supported targets and package",
        "## Install with Herdr",
        "## Start, status, stop, and restart",
        "## Disable",
        "## Unlink",
        "## Remove",
        "## Update activation",
        "## Failed-update recovery",
        "## Configuration and diagnostics",
    ];
    assert_ordered(LIFECYCLE, &headings);

    let mut unique = BTreeSet::new();
    for heading in headings {
        assert!(unique.insert(heading));
        assert!(!section_body(LIFECYCLE, heading).trim().is_empty());
    }
}

#[test]
fn lifecycle_document_proves_ordinary_install_and_explicit_actions() {
    let install = numbered_steps(&section_body(LIFECYCLE, "## Install with Herdr"));
    assert!(install.len() >= 4, "install procedure is not complete: {install:?}");
    assert_ordered(
        &install.join("\n"),
        &[
            "Install the selected known release through Herdr",
            "Herdr places the plugin under HERDR_PLUGIN_ROOT",
            "No additional configuration is required",
            "Use the plugin's startup action",
        ],
    );

    let lifecycle = numbered_steps(&section_body(
        LIFECYCLE,
        "## Start, status, stop, and restart",
    ));
    assert!(lifecycle.len() >= 4, "lifecycle procedure is not complete: {lifecycle:?}");
    assert_ordered(
        &lifecycle.join("\n"),
        &[
            "Invoke start",
            "Invoke status",
            "Invoke stop",
            "Invoke restart",
        ],
    );
    assert!(
        section_body(LIFECYCLE, "## Start, status, stop, and restart")
            .to_ascii_lowercase()
            .contains("read-only")
    );
}

#[test]
fn lifecycle_document_requires_successful_stop_before_each_removal_operation() {
    for heading in ["## Disable", "## Unlink", "## Remove"] {
        let body = section_body(LIFECYCLE, heading);
        let steps = numbered_steps(&body);
        assert!(steps.len() >= 3, "{heading} procedure is not complete: {steps:?}");
        assert_ordered(&steps.join("\n"), &["Invoke stop", "Confirm a successful stop", "Invoke"]);
        assert!(
            body.contains("does not stop an already-running bridge"),
            "{heading} must not imply that Herdr stops a live bridge"
        );
    }
    let removal = format!(
        "{}\n{}\n{}",
        section_body(LIFECYCLE, "## Disable"),
        section_body(LIFECYCLE, "## Unlink"),
        section_body(LIFECYCLE, "## Remove")
    );
    assert!(!removal.contains("automatically stops"));
    assert!(!removal.contains("automatic stop by Herdr"));
}

#[test]
fn lifecycle_document_binds_update_and_recovery_order() {
    let update = section_body(LIFECYCLE, "## Update activation");
    assert_ordered(
        &update,
        &[
            "explicit restart",
            "next Herdr start",
            "old bridge authority ends",
            "fresh USB, Herdr, and Codex sessions",
        ],
    );
    assert!(!update.contains("live handoff"));
    assert!(!update.contains("immediate automatic activation"));

    let recovery = section_body(LIFECYCLE, "## Failed-update recovery");
    let steps = numbered_steps(&recovery);
    assert!(steps.len() >= 5, "recovery procedure is not complete: {steps:?}");
    assert_ordered(
        &steps.join("\n"),
        &[
            "Invoke stop",
            "manually reinstall one specifically selected known plugin release through Herdr",
            "Invoke start",
            "Invoke status",
        ],
    );
    assert!(recovery.contains("No automatic rollback"));
}

#[test]
fn lifecycle_document_is_symbolic_and_privacy_bounded() {
    for forbidden in [
        "/home/",
        "/Users/",
        "/tmp/",
        "127.0.0.1",
        "localhost",
        "BEGIN OPENSSH",
        "sk-",
        "account_id",
        "transcript",
        "prompt",
        "raw error",
        "diagnostic payload",
    ] {
        assert!(!LIFECYCLE.contains(forbidden), "document contains forbidden {forbidden:?}");
    }
    for required in [
        "HERDR_PLUGIN_ROOT",
        "HERDR_PLUGIN_CONFIG_DIR",
        "HERDR_PLUGIN_STATE_DIR",
        "Linux x86-64",
        "macOS Apple Silicon",
        "bounded",
        "stderr",
    ] {
        assert!(LIFECYCLE.contains(required), "document omits {required:?}");
    }
}
