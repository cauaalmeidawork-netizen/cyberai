import { describe, expect, it } from "vitest";

import { linkifyCitations } from "./citations";

describe("linkifyCitations", () => {
  it("returns the content unchanged when there are no sources", () => {
    expect(linkifyCitations("foo [1] bar", 0)).toBe("foo [1] bar");
  });

  it("links standalone citation markers within range", () => {
    expect(linkifyCitations("KEV em 2024 [1]", 2)).toBe("KEV em 2024 [1](#citation-1)");
  });

  it("leaves markers outside the source range untouched", () => {
    expect(linkifyCitations("veja [3]", 2)).toBe("veja [3]");
  });

  it("does not rewrite array indices like foo[1]", () => {
    expect(linkifyCitations("use array[1] here", 3)).toBe("use array[1] here");
  });

  it("does not rewrite markdown links [text](url)", () => {
    expect(linkifyCitations("see [docs](https://example.com)", 3)).toBe(
      "see [docs](https://example.com)",
    );
  });

  it("handles adjacent citations [1][2]", () => {
    expect(linkifyCitations("explorada [1][2]", 3)).toBe(
      "explorada [1](#citation-1)[2](#citation-2)",
    );
  });

  it("does not touch citations inside fenced code blocks", () => {
    const content = "before\n```\nconst a = [1]\n```\nafter [1]";
    expect(linkifyCitations(content, 2)).toBe(
      "before\n```\nconst a = [1]\n```\nafter [1](#citation-1)",
    );
  });
});
