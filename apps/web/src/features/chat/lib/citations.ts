const CITATION_RE = /(?<![A-Za-z0-9])\[(\d{1,2})\](?!\()/g;

export function linkifyCitations(markdown: string, sourceCount: number): string {
  if (sourceCount < 1 || !markdown.includes("[")) {
    return markdown;
  }

  const lines = markdown.split("\n");
  let inFence = false;
  const output: string[] = [];

  for (const line of lines) {
    const trimmed = line.trimStart();
    const isFence = trimmed.startsWith("```") || trimmed.startsWith("````");
    if (isFence) {
      inFence = !inFence;
      output.push(line);
      continue;
    }
    if (inFence) {
      output.push(line);
      continue;
    }
    output.push(
      line.replace(CITATION_RE, (match, digits: string) => {
        const index = Number(digits);
        if (index < 1 || index > sourceCount) return match;
        return `[${digits}](#citation-${index})`;
      }),
    );
  }

  return output.join("\n");
}
