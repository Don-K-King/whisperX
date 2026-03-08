function decodeBase64(value){
  if (typeof atob === 'function') {
    return atob(value);
  }
  return Buffer.from(value, 'base64').toString('utf-8');
}

export function parseToken(token){
  const [, payload] = token.split('.');
  if (!payload) return { token, tenant_id: 'unknown', roles: ['user'] };
  try {
    const claims = JSON.parse(decodeBase64(payload));
    return { token, tenant_id: claims.tenant_id ?? 'unknown', roles: claims.roles ?? ['user'] };
  } catch {
    return { token, tenant_id: 'unknown', roles: ['user'] };
  }
}

export function sanitizedError(problem){
  return `${problem.error_code ?? 'unknown_error'}${problem.correlation_id ? ` (${problem.correlation_id})` : ''}`;
}
