// @ts-nocheck
/**
 * Terms of Service and Privacy Policy stubs.
 * Replace with real content before launch.
 */
import { useParams, Link } from 'react-router-dom'

const LEGAL = {
  terms: {
    title: 'Terms of Service',
    lastUpdated: 'April 2026',
    content: `
**dgraph.ai Terms of Service**

These Terms of Service ("Terms") govern your access to and use of dgraph.ai services.
By signing up, you agree to be bound by these Terms.

**1. Acceptance**
By creating an account, you confirm that you are at least 18 years old and have the authority to bind your organization to these Terms.

**2. Service Description**
dgraph.ai provides a data intelligence platform that indexes and analyzes files from connected data sources. You retain ownership of all data indexed through the platform.

**3. Data Processing**
We process your data only as necessary to provide the Service. See our Privacy Policy for details on how we handle personal data.

**4. Acceptable Use**
You agree not to use the Service to violate any applicable law, infringe any intellectual property rights, or harm any third party.

**5. Payment**
Paid plans are billed in advance. Refunds are provided at our discretion. We reserve the right to suspend accounts with overdue payments.

**6. Termination**
Either party may terminate this agreement at any time. Upon termination, we will delete your data within 72 hours.

**7. Limitation of Liability**
To the maximum extent permitted by law, dgraph.ai shall not be liable for any indirect, incidental, or consequential damages.

**8. Changes**
We may update these Terms at any time. We will notify you by email of material changes.

**Contact:** legal@dgraph.ai
    `.trim(),
  },
  privacy: {
    title: 'Privacy Policy',
    lastUpdated: 'April 2026',
    content: `
**dgraph.ai Privacy Policy**

This Privacy Policy describes how dgraph.ai ("we," "us," "our") collects, uses, and protects information.

**1. Information We Collect**
- Account information: name, email address, company name
- Usage data: queries run, features used, login timestamps
- File metadata: file names, sizes, types, modification dates (never file content in SaaS mode)
- AI enrichment results: summaries, detected patterns, classifications

**2. How We Use Information**
- To provide and improve the Service
- To send transactional emails (verification, security alerts)
- To send onboarding and product update emails (you may opt out)
- To comply with legal obligations

**3. Data Sharing**
We do not sell your data. We share data only with:
- Service providers (AWS, Neo4j) under data processing agreements
- Law enforcement when required by applicable law

**4. Data Retention**
We retain your data for as long as your account is active. Upon account deletion, data is erased within 72 hours per GDPR Article 17.

**5. Your Rights (GDPR)**
If you are in the EU/EEA, you have the right to:
- Access your personal data
- Correct inaccurate data
- Request erasure ("right to be forgotten")
- Data portability
- Lodge a complaint with your supervisory authority

Exercise these rights at: privacy@dgraph.ai or via Settings → Danger Zone.

**6. Security**
We use TLS 1.3, bcrypt password hashing, and Ed25519 cryptographic signing. We undergo regular security reviews.

**7. Contact**
Data Controller: dgraph.ai, Inc.
Email: privacy@dgraph.ai
    `.trim(),
  },
}

export function LegalPage() {
  const { type } = useParams<{ type: 'terms' | 'privacy' }>()
  const page = LEGAL[type ?? 'terms'] ?? LEGAL.terms

  return (
    <div style={{
      minHeight: '100vh', background: '#0a0a0f', padding: '40px 24px',
      display: 'flex', justifyContent: 'center',
    }}>
      <div style={{ maxWidth: 720, width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 32 }}>
          <Link to="/" style={{ textDecoration: 'none' }}>
            <div style={{ width: 32, height: 32, borderRadius: 8, background: '#4f8ef7', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: 13 }}>dg</div>
          </Link>
          <span style={{ fontSize: 16, fontWeight: 700, color: '#e2e2f0' }}>dgraph.ai</span>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 32 }}>
          <Link to="/legal/terms" style={{ textDecoration: 'none', padding: '6px 14px', borderRadius: 7, background: type === 'terms' ? '#4f8ef7' : '#12121a', color: type === 'terms' ? '#fff' : '#8888aa', fontSize: 13, fontWeight: 600, border: '1px solid ' + (type === 'terms' ? '#4f8ef7' : '#252535') }}>
            Terms of Service
          </Link>
          <Link to="/legal/privacy" style={{ textDecoration: 'none', padding: '6px 14px', borderRadius: 7, background: type === 'privacy' ? '#4f8ef7' : '#12121a', color: type === 'privacy' ? '#fff' : '#8888aa', fontSize: 13, fontWeight: 600, border: '1px solid ' + (type === 'privacy' ? '#4f8ef7' : '#252535') }}>
            Privacy Policy
          </Link>
        </div>

        <h1 style={{ fontSize: 28, fontWeight: 800, color: '#e2e2f0', marginBottom: 8 }}>{page.title}</h1>
        <p style={{ fontSize: 12, color: '#35354a', marginBottom: 32 }}>Last updated: {page.lastUpdated}</p>

        <div style={{ color: '#8888aa', fontSize: 14, lineHeight: 1.8 }}>
          {page.content.split('\n').map((line, i) => {
            if (line.startsWith('**') && line.endsWith('**') && !line.slice(2, -2).includes('**')) {
              return <h3 key={i} style={{ color: '#d0d0e8', fontWeight: 700, marginTop: 24, marginBottom: 8 }}>{line.slice(2, -2)}</h3>
            }
            if (line.startsWith('- ')) {
              return <li key={i} style={{ marginLeft: 20 }}>{line.slice(2)}</li>
            }
            if (!line.trim()) return <br key={i} />
            return <p key={i} style={{ margin: '4px 0' }}>{line}</p>
          })}
        </div>

        <div style={{ marginTop: 48, paddingTop: 24, borderTop: '1px solid #1a1a28', display: 'flex', gap: 16 }}>
          <Link to="/login" style={{ color: '#4f8ef7', fontSize: 12, textDecoration: 'none' }}>Sign in</Link>
          <Link to="/signup" style={{ color: '#4f8ef7', fontSize: 12, textDecoration: 'none' }}>Create account</Link>
          <a href="mailto:legal@dgraph.ai" style={{ color: '#4f8ef7', fontSize: 12, textDecoration: 'none' }}>legal@dgraph.ai</a>
        </div>
      </div>
    </div>
  )
}
