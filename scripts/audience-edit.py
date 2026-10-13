from pathlib import Path
import re
root=Path('/home/ubuntu/worktrees/ui-audit-d-audience')
def edit(route, fn):
 p=root/'src/routes'/route/'+page.svelte'; old=p.read_text(); new=fn(old); assert new!=old, route; p.write_text(new)
def following(s):
 s=s.replace('box-shadow: inset 3px 0 0 #ffd060;', 'background: var(--chip-warn-bg);\n    color: var(--chip-warn-fg);\n    outline: 1px solid var(--chip-warn-border);\n    outline-offset: -1px;')
 colors={'#4caf50':'success','#3fb950':'success','#48bb78':'success','#ef5350':'error','#c62828':'error','#ffd060':'warn','#ef9a3':'info','#a082dc':'brand','#fb923c':'warn','#ed8936':'warn'}
 for color,kind in colors.items(): s=s.replace(color,f'var(--chip-{kind}-fg)')
 rgba={'76, 175, 80':'success','255, 180, 0':'warn','99, 179, 237':'info','239, 83, 80':'error','72, 187, 120':'success','160, 130, 220':'brand','251, 146, 60':'warn','237, 137, 54':'warn','250, 204, 21':'warn','255, 208, 96':'warn'}
 for rgb,kind in rgba.items():
  s=re.sub(r'rgba\('+rgb+r', [\d.]+\)',lambda m:f'var(--chip-{kind}-'+('border' if '0.35' in m[0] or '0.25' in m[0] else 'bg')+')',s)
 s=s.replace('rgba(107, 101, 96, 0.2)','var(--surface2)').replace('color: #fff;','color: var(--text);')
 # Badge-like blocks need the full semantic triad.
 s=re.sub(r'(  [^{}]+\{\n)([^{}]*background: var\(--chip-(\w+)-bg\);[^{}]*)(\n  \})',lambda m:m[1]+m[2]+(f'\n    border: 1px solid var(--chip-{m[3]}-border);' if 'border:' not in m[2] and 'outline:' not in m[2] else '')+m[4],s)
 return s
edit('following',following)
def showcase(s):
 for a,b in {'#0f0f1a':'var(--bg)','#e5e5f0':'var(--text)','#1a1a2e':'var(--surface)','rgba(255, 255, 255, 0.08)':'var(--border)','#a78bfa':'var(--chip-brand-fg)','rgba(167, 139, 250, 0.16)':'var(--chip-brand-bg)','#c4b5fd':'var(--chip-brand-fg)','rgba(167, 139, 250, 0.4)':'var(--chip-brand-border)','#b0b0c0':'var(--text-dim)','rgba(255, 255, 255, 0.03)':'var(--surface2)','#22c55e':'var(--chip-success-fg)',"-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif":'var(--font-body)'}.items():s=s.replace(a,b)
 return s.replace('.showcase-cell h3 {','.showcase-cell h3 {\n    font-family: var(--font-heading);')
edit('showcase',showcase)
def hub(s):
 s=s.replace('margin-inline: auto;','margin-inline: auto;\n    padding-inline: var(--layout-pad);',1)
 s=s.replace('<table class="dns-table">','<div class="dns-table-wrap" tabindex="0" role="region" aria-label="DNS records">\n                  <table class="dns-table">',1)
 pos=s.index('<div class="dns-table-wrap"'); end=s.index('</table>',pos)+len('</table>'); s=s[:end]+ '\n                  </div>'+s[end:]
 s=s.replace('  .dns-table {','  .dns-table-wrap {\n    max-width: 100%;\n    overflow-x: auto;\n  }\n\n  .dns-table {',1)
 for a,b in {'#fff':'var(--text)','#ffd060':'var(--chip-warn-fg)','#ef5350':'var(--chip-error-fg)','rgba(255, 180, 0, 0.1)':'var(--chip-warn-bg)','rgba(255, 180, 0, 0.08)':'var(--chip-warn-bg)','rgba(255, 180, 0, 0.3)':'var(--chip-warn-border)'}.items():s=s.replace(a,b)
 return s
edit('handle-hub',hub)
def dm(s):
 s=s.replace("  import InboxPanel", "  import LockedFeature from '$lib/components/LockedFeature.svelte';\n  import InboxPanel",1)
 s=s.replace("return 'default';","return 'campaign-active';",1).replace("case 'paused':\n        return 'secondary';","case 'paused':\n        return 'campaign-paused';").replace("case 'completed':\n        return 'outline';","case 'completed':\n        return 'campaign-completed';").replace("case 'draft':\n        return 'secondary';","case 'draft':\n        return 'campaign-draft';").replace("default:\n        return 'secondary';","default:\n        return 'campaign-draft';",1)
 s=s.replace('<Badge variant={getStatusColor(campaign.status)}>','<Badge variant="outline" class={getStatusColor(campaign.status)}>')
 s=s.replace('    <section class="card">\n      <h1>DM Studio</h1>\n    </section>','''    <LockedFeature
      featureKey="dm_studio"
      title="DM Studio"
      description="Manage your inbox, outreach campaigns, and reusable message templates. Unlock DM Studio with a supported creator plan."
      status={data.featureAccess.status}
      reason={data.featureAccess.reason}
      minTier={data.featureAccess.minTier}
      requiresVerification={data.featureAccess.requiresVerification}
    />''')
 s=s.replace('onclick={() => openEditTemplate(template)}','aria-label={`Edit template: ${template.label}`}\n                            onclick={() => openEditTemplate(template)}').replace('onclick={() => deleteTemplate(template.id)}','aria-label={`Delete template: ${template.label}`}\n                            onclick={() => deleteTemplate(template.id)}')
 css=''
 for name,kind in [('active','success'),('paused','warn'),('completed','info'),('draft','brand')]:css+=f'  :global(.campaign-{name}) {{\n    background: var(--chip-{kind}-bg);\n    color: var(--chip-{kind}-fg);\n    border-color: var(--chip-{kind}-border);\n  }}\n'
 return s.replace('<style>','<style>\n'+css,1)
edit('dm-studio',dm)
def silent(s):
 for a,b in {'bg-green-50 dark:bg-green-950/20':'category-success','bg-amber-50 dark:bg-amber-950/20':'category-warn','bg-slate-50 dark:bg-slate-900/20':'category-neutral','bg-blue-50 dark:bg-blue-950/20':'category-info','text-green-600 dark:text-green-400':'text-[var(--chip-success-fg)]','text-amber-600 dark:text-amber-400':'text-[var(--chip-warn-fg)]','text-slate-600 dark:text-slate-400':'text-[var(--text-dim)]','text-blue-600 dark:text-blue-400':'text-[var(--chip-info-fg)]'}.items():s=s.replace(a,b)
 s=re.sub(r'\n            <div class="people-count">.*?</div>','',s,flags=re.S)
 s=re.sub(r'  \.people-count[^{}]*\{[^{}]*\}\n','',s)
 s=s.replace('  .classification-card {','  .classification-card {\n    background: var(--surface);')
 css='  .category-neutral {\n    background: var(--surface2);\n    color: var(--text-dim);\n  }\n'
 for kind in ['success','warn','info']:css+=f'  .classification-card.category-{kind} {{\n    background: var(--chip-{kind}-bg);\n    border-color: var(--chip-{kind}-border);\n    color: var(--chip-{kind}-fg);\n  }}\n'
 return s.replace('<style>','<style>\n'+css,1)
edit('audience/silent-mutuals',silent)
def subs(s):
 s=s.replace('max-width: 960px;','max-width: var(--page-w-standard);')
 s=re.sub(r'var\(--muted-foreground, #[a-f0-9]+\)','var(--text-dim)',s)
 s=re.sub(r'var\(--border, #[a-f0-9]+\)','var(--border)',s)
 s=s.replace('var(--destructive, #d33)','var(--chip-error-fg)')
 for old,new in [('success-bg','chip-success-bg'),('success-fg','chip-success-fg'),('warning-bg','chip-warn-bg'),('warning-fg','chip-warn-fg')]:s=re.sub(r'var\(--'+old+r', #[a-f0-9]+\)',f'var(--{new})',s)
 s=s.replace('.sx-tier-exact {','.sx-tier-exact {\n    border: 1px solid var(--chip-success-border);').replace('.sx-tier-fuzzy {','.sx-tier-fuzzy {\n    border: 1px solid var(--chip-warn-border);')
 return s
edit('audience/subscribers',subs)
edit('lobby',lambda s:s.replace('    Sparkles,\n','').replace('<Sparkles ','<Rss '))
def inspiration(s):
 s=re.sub(r'                  <button\n                    type="button"\n                    class="shrink-0[^\n]+\n                    aria-label="Copy idea: \{line\}".*?</button>\n','',s,flags=re.S)
 return s.replace('  @keyframes shine {','  @media (prefers-reduced-motion: reduce) {\n    :global(.generate-btn:hover) .generate-shine,\n    :global(.generate-btn:focus-visible) .generate-shine {\n      animation: none;\n    }\n    .spotlight {\n      transition: none;\n    }\n  }\n\n  @keyframes shine {',1)
edit('inspiration',inspiration)
