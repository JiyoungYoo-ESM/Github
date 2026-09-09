#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { EsmStack } from '../lib/esm-stack';
import { CicdStack } from '../lib/cicd-stack';

const app = new cdk.App();

const account = process.env.CDK_DEFAULT_ACCOUNT ?? '634236767858';
const region = process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-2';
const env = { account, region };

const vpcId = app.node.tryGetContext('vpcId') ?? 'vpc-0b52fdfc0139395d2';

// Per-env extra origins, e.g. `cdk deploy esm-prd -c prdOrigins=https://esm.example.com`.
const originsFor = (e: string): string[] =>
  String(app.node.tryGetContext(`${e}Origins`) ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

new CicdStack(app, 'esm-cicd', {
  env,
  // The account already has the GitHub OIDC provider; reuse it by default.
  existingOidcProviderArn:
    app.node.tryGetContext('oidcProviderArn') ??
    `arn:aws:iam::${account}:oidc-provider/token.actions.githubusercontent.com`,
});

const HOSTNAMES: Record<string, string> = {
  dev: 'esm-dev.siliconii.com',
  prd: 'esm.siliconii.com',
};
// ACM certs (ap-northeast-2, DNS-validated). Defaults so every deploy keeps the
// 443 listener; override with `-c devCertArn=`/`-c prdCertArn=`. NOTE: the 443
// listener only deploys once the cert is ISSUED (add the DNS validation record).
const CERT_ARNS: Record<string, string> = {
  dev: 'arn:aws:acm:ap-northeast-2:634236767858:certificate/2e0306a6-21a4-42cb-809f-3263176acdfe',
  prd: 'arn:aws:acm:ap-northeast-2:634236767858:certificate/1c91a172-7945-41ef-bfa1-5710ae8756d7',
};

new EsmStack(app, 'esm-dev', {
  env, envName: 'dev', vpcId,
  extraOrigins: originsFor('dev'),
  hostname: HOSTNAMES.dev,
  certArn: app.node.tryGetContext('devCertArn') ?? CERT_ARNS.dev,
});
new EsmStack(app, 'esm-prd', {
  env, envName: 'prd', vpcId,
  extraOrigins: originsFor('prd'),
  hostname: HOSTNAMES.prd,
  certArn: app.node.tryGetContext('prdCertArn') ?? CERT_ARNS.prd,
});
