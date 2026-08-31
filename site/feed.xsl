<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" encoding="UTF-8" indent="yes"/>
  <xsl:template match="/rss/channel">
    <html lang="en">
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="title"/> — RSS</title>
        <style type="text/css">
          :root {
            --bg: #efe8da;
            --paper: #fffcf6;
            --ink: #14120e;
            --body: #2a261e;
            --muted: #6a6458;
            --accent: #8c2f12;
            --rule: rgba(22, 20, 16, 0.12);
          }
          * { box-sizing: border-box; }
          html, body {
            margin: 0;
            background: var(--bg);
            color: var(--body);
            font-family: Georgia, "Times New Roman", serif;
          }
          a { color: var(--accent); }
          .wrap {
            max-width: 42rem;
            margin: 0 auto;
            padding: 2rem 1.25rem 4rem;
          }
          .kicker {
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-size: 0.72rem;
            color: var(--muted);
            font-family: "Segoe UI", sans-serif;
            margin: 0 0 0.4rem;
          }
          h1 {
            font-size: 2rem;
            color: var(--ink);
            margin: 0 0 0.5rem;
          }
          .dek, .updated {
            color: var(--muted);
            margin: 0 0 0.75rem;
          }
          .note {
            background: var(--paper);
            border: 1px solid var(--rule);
            border-radius: 12px;
            padding: 0.85rem 1rem;
            font-family: "Segoe UI", sans-serif;
            font-size: 0.92rem;
            margin: 1.25rem 0 2rem;
          }
          article {
            background: var(--paper);
            border: 1px solid var(--rule);
            border-radius: 16px;
            padding: 1.1rem 1.15rem 1.2rem;
            margin: 0 0 1rem;
          }
          article h2 {
            font-size: 1.15rem;
            line-height: 1.35;
            margin: 0 0 0.35rem;
          }
          article h2 a { text-decoration: none; color: var(--ink); }
          article h2 a:hover { color: var(--accent); }
          time {
            display: block;
            font-family: "Segoe UI", sans-serif;
            font-size: 0.78rem;
            color: var(--muted);
            margin-bottom: 0.55rem;
          }
          article p {
            margin: 0;
            white-space: pre-wrap;
            line-height: 1.45;
          }
        </style>
      </head>
      <body>
        <div class="wrap">
          <p class="kicker">RSS feed</p>
          <h1><xsl:value-of select="title"/></h1>
          <p class="dek"><xsl:value-of select="description"/></p>
          <p class="updated">Updated <xsl:value-of select="lastBuildDate"/></p>
          <p class="note">
            This is a live RSS feed. Subscribe in Feedly or any reader using
            this page’s URL, or
            <a href="https://ai-daily-intelligence.pages.dev/">open the briefing</a>.
          </p>
          <xsl:for-each select="item">
            <article>
              <h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
              <time><xsl:value-of select="pubDate"/></time>
              <p><xsl:value-of select="description"/></p>
            </article>
          </xsl:for-each>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
