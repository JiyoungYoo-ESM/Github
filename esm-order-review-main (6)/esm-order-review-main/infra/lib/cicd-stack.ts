import { Stack, StackProps, RemovalPolicy, Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecr from 'aws-cdk-lib/aws-ecr';

const GITHUB_REPO = 'siliconii-vibe/esm-order-review';
const DEPLOY_BRANCHES = ['develop', 'main'];
// The only workflow allowed to assume the role. A new workflow file — or the
// app workflow run from any other branch — gets no credentials.
const DEPLOY_WORKFLOW = '.github/workflows/deploy.yml';
// Immutable numeric ids: survive a rename, and a deleted/recreated repo of the
// same name would get new ids and stop matching.
const GITHUB_REPO_ID = '1256707919';
const GITHUB_OWNER_ID = '289853604';

export interface CicdStackProps extends StackProps {
  /** Pass an existing provider ARN if the account already has the GitHub OIDC provider. */
  existingOidcProviderArn?: string;
}

/**
 * GitHub Actions OIDC deploy role — **app pipeline only**.
 *
 * It can push images to ECR and force a new ECS deployment. It deliberately
 * CANNOT run cdk: no sts:AssumeRole on the cdk bootstrap roles, no bootstrap
 * SSM read. Infrastructure changes are deployed locally with admin/SSO
 * (see infra/README.md), never from CI.
 *
 * Deploy this stack once locally before CI can run.
 */
export class CicdStack extends Stack {
  constructor(scope: Construct, id: string, props: CicdStackProps = {}) {
    super(scope, id, props);

    const providerArn =
      props.existingOidcProviderArn ??
      new iam.OpenIdConnectProvider(this, 'GithubOidc', {
        url: 'https://token.actions.githubusercontent.com',
        clientIds: ['sts.amazonaws.com'],
      }).openIdConnectProviderArn;

    const ecsServiceArns = ['dev', 'prd'].flatMap((e) => [
      `arn:aws:ecs:${this.region}:${this.account}:service/sk-${e}-an2-ecs-cls-esm/sk-${e}-an2-ecs-svc-esm`,
      `arn:aws:ecs:${this.region}:${this.account}:service/sk-${e}-an2-ecs-cls-esm/sk-${e}-an2-ecs-svc-worker-esm`,
    ]);

    // Hard ceiling on the role: effective permissions are the intersection of
    // its policies and this boundary, so attaching another policy later (by
    // hand or by a future stack edit) still cannot grant iam/cloudformation/
    // ec2/rds/secretsmanager or any other infra mutation. The repo ARNs use a
    // wildcard rather than the repo objects to avoid a cyclic dependency.
    const boundary = new iam.ManagedPolicy(this, 'DeployRoleBoundary', {
      managedPolicyName: 'sk-an2-pb-esm-github-deploy',
      description: 'Max permissions for the GitHub Actions app deploy role',
      statements: [
        new iam.PolicyStatement({
          actions: ['ecr:GetAuthorizationToken'],
          resources: ['*'],
        }),
        new iam.PolicyStatement({
          actions: [
            'ecr:BatchCheckLayerAvailability',
            'ecr:GetDownloadUrlForLayer',
            'ecr:BatchGetImage',
            'ecr:InitiateLayerUpload',
            'ecr:UploadLayerPart',
            'ecr:CompleteLayerUpload',
            'ecr:PutImage',
          ],
          resources: [
            `arn:aws:ecr:${this.region}:${this.account}:repository/sk-dev-an2-ecr-esm-*`,
            `arn:aws:ecr:${this.region}:${this.account}:repository/sk-prd-an2-ecr-esm-*`,
          ],
        }),
        new iam.PolicyStatement({
          actions: ['ecs:UpdateService', 'ecs:DescribeServices'],
          resources: ecsServiceArns,
        }),
      ],
    });

    const role = new iam.Role(this, 'DeployRole', {
      permissionsBoundary: boundary,
      roleName: 'sk-an2-role-esm-github-deploy',
      // ASCII only: IAM rejects non-ASCII (em dash) in role descriptions.
      description: 'GitHub Actions app deploy (ECR + ECS) - no infra/cdk access',
      maxSessionDuration: Duration.hours(1),
      // Exact-match trust: this repo (by id), these branches, this workflow file.
      assumedBy: new iam.WebIdentityPrincipal(providerArn, {
        StringEquals: {
          'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
          'token.actions.githubusercontent.com:repository': GITHUB_REPO,
          'token.actions.githubusercontent.com:repository_id': GITHUB_REPO_ID,
          'token.actions.githubusercontent.com:repository_owner_id': GITHUB_OWNER_ID,
          'token.actions.githubusercontent.com:sub': DEPLOY_BRANCHES.map(
            (b) => `repo:${GITHUB_REPO}:ref:refs/heads/${b}`,
          ),
          'token.actions.githubusercontent.com:job_workflow_ref': DEPLOY_BRANCHES.map(
            (b) => `${GITHUB_REPO}/${DEPLOY_WORKFLOW}@refs/heads/${b}`,
          ),
        },
      }),
    });

    // ECR repos per env/component. The app pipeline pushes :latest + :<sha>;
    // the ECS task definitions reference :latest.
    const repos: ecr.Repository[] = [];
    for (const e of ['dev', 'prd']) {
      for (const c of ['backend', 'frontend']) {
        repos.push(
          new ecr.Repository(this, `Repo-${c}-${e}`, {
            repositoryName: `sk-${e}-an2-ecr-esm-${c}`,
            imageScanOnPush: true,
            lifecycleRules: [{ maxImageCount: 15 }],
            removalPolicy: RemovalPolicy.RETAIN,
          }),
        );
      }
    }

    // --- App path only. Anything cdk needs is intentionally absent. ---
    // Docker login. GetAuthorizationToken has no resource scope in IAM.
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ['ecr:GetAuthorizationToken'],
        resources: ['*'],
      }),
    );
    repos.forEach((r) => r.grantPullPush(role));
    // force-new-deployment + `aws ecs wait services-stable`, on these services
    // only. UpdateService is the one mutating call the app pipeline needs; IAM
    // has no condition key to narrow it to force-new-deployment, so the boundary
    // above keeps it from ever reaching another cluster or service.
    role.addToPolicy(
      new iam.PolicyStatement({
        actions: ['ecs:UpdateService', 'ecs:DescribeServices'],
        resources: ecsServiceArns,
      }),
    );
  }
}
