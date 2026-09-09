import {
  Stack,
  StackProps,
  Duration,
  RemovalPolicy,
  CfnOutput,
} from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as ecs from 'aws-cdk-lib/aws-ecs';
import * as ecr from 'aws-cdk-lib/aws-ecr';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as elasticache from 'aws-cdk-lib/aws-elasticache';

// backend/config.py + auth/user_store.py: the login-hash env vars the app reads.
const AUTH_HASH_KEYS = [
  'AUTH_ADMINMASTER_PASSWORD_HASH',
  'AUTH_EU_MANAGER_PASSWORD_HASH',
  'AUTH_BM1_PASSWORD_HASH',
  'AUTH_BM2_PASSWORD_HASH',
  'AUTH_BM3_PASSWORD_HASH',
  'AUTH_HNB_TEAM_PASSWORD_HASH',
  'AUTH_IA_PASSWORD_HASH',
  'AUTH_MY_TEAM_PASSWORD_HASH',
  'AUTH_VN_TEAM_PASSWORD_HASH',
  'AUTH_MINWOO_PASSWORD_HASH',
  'AUTH_SALES_TEAM_PASSWORD_HASH',
] as const;

export interface EsmStackProps extends StackProps {
  envName: 'dev' | 'prd';
  vpcId: string;
  /** Extra CORS/frontend origins. The ALB DNS (and https hostname, if set) are always added. */
  extraOrigins?: string[];
  /** Public hostname, e.g. esm.siliconii.com — added to CORS origins as https://. */
  hostname?: string;
  /** ACM cert ARN (same region). When set, adds a 443 listener + redirects 80->443. */
  certArn?: string;
}

/** One self-contained ECS cluster + service + ALB + RDS + S3 per environment. */
export class EsmStack extends Stack {
  constructor(scope: Construct, id: string, props: EsmStackProps) {
    super(scope, id, props);
    const { envName } = props;
    const isProd = envName === 'prd';
    // Naming convention: sk-<env>-an2-<type>-esm
    const n = (type: string) => `sk-${envName}-an2-${type}-esm`;

    const vpc = ec2.Vpc.fromLookup(this, 'Vpc', { vpcId: props.vpcId });

    // --- S3: durable analysis outputs (raw uploads stay ephemeral on the task). ---
    const bucket = new s3.Bucket(this, 'Outputs', {
      bucketName: `${n('s3')}-${this.account}`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      removalPolicy: isProd ? RemovalPolicy.RETAIN : RemovalPolicy.DESTROY,
      autoDeleteObjects: !isProd,
    });

    // --- RDS PostgreSQL (one instance per environment). ---
    const dbSg = new ec2.SecurityGroup(this, 'DbSg', {
      vpc,
      allowAllOutbound: false,
      securityGroupName: `${n('sg')}-db`,
    });
    const db = new rds.DatabaseInstance(this, 'Db', {
      engine: rds.DatabaseInstanceEngine.postgres({
        version: rds.PostgresEngineVersion.VER_16,
      }),
      vpc,
      // Isolated DB tier of sk-vibe-vpc-workload (no egress; RDS doesn't need it).
      vpcSubnets: { subnetGroupName: 'iso-db' },
      instanceIdentifier: n('rds'),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO),
      allocatedStorage: 20,
      maxAllocatedStorage: 100,
      multiAz: isProd,
      databaseName: `esm_${envName}`,
      credentials: rds.Credentials.fromGeneratedSecret('esm', {
        secretName: `${n('sm')}-rds`,
      }),
      securityGroups: [dbSg],
      publiclyAccessible: false,
      storageEncrypted: true,
      backupRetention: Duration.days(isProd ? 7 : 1),
      deletionProtection: isProd,
      removalPolicy: isProd ? RemovalPolicy.SNAPSHOT : RemovalPolicy.DESTROY,
    });

    // --- ElastiCache Redis: rate-limit/concurrency state + Celery broker. ---
    const redisSg = new ec2.SecurityGroup(this, 'RedisSg', {
      vpc,
      allowAllOutbound: false,
      securityGroupName: `${n('sg')}-redis`,
    });
    const redisSubnets = new elasticache.CfnSubnetGroup(this, 'RedisSubnets', {
      cacheSubnetGroupName: `${n('ec')}-subnets`,
      description: `esm ${envName} redis subnets (iso-db)`,
      subnetIds: vpc.selectSubnets({ subnetGroupName: 'iso-db' }).subnetIds,
    });
    const redis = new elasticache.CfnCacheCluster(this, 'Redis', {
      clusterName: n('ec'),
      engine: 'redis',
      // ponytail: single node, no TLS/failover — scale up = bump cacheNodeType
      // (brief interruption); move to CfnReplicationGroup if HA/TLS is needed.
      cacheNodeType: 'cache.t4g.micro',
      numCacheNodes: 1,
      cacheSubnetGroupName: redisSubnets.ref,
      vpcSecurityGroupIds: [redisSg.securityGroupId],
    });
    const redisUrl = `redis://${redis.attrRedisEndpointAddress}:${redis.attrRedisEndpointPort}/0`;

    // --- App secret: login hashes. STATIC generateSecretString template (never
    // changes between deploys), so CDK only sets it at CREATE and never
    // regenerates/clobbers it afterwards. The nine AUTH_* keys are seeded with a
    // temp-password hash (rotate to real hashes out-of-band via put-secret-value;
    // rotations survive because the template stays constant). Must stay literally
    // constant — changing it regenerates the secret and wipes the hashes. ---
    const SEED_HASH =
      'pbkdf2_sha256$600000$qfdj9CTeTWxgzsCFKmFCZw$2zlR97Wb5emmpVgSUG_lwc9x_A3ZfU6kT6Rd0QW2Sro';
    // Historical per-user seed hash. Keep this template stable while retiring
    // the old secret key through the deployment secret-management procedure.
    const MINWOO_HASH =
      'pbkdf2_sha256$600000$LkG9cplJ5dcBQCEBodRlCw$nC9I1HeEi5tpZxfDUnUU6xKSdpfJ_QtDZQSNMqV7ghs';
    const appSecret = new secretsmanager.Secret(this, 'AppSecret', {
      secretName: `${n('sm')}-app`,
      description: `esm ${envName} runtime secrets (login hashes, etc.)`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify(
          Object.fromEntries(
            AUTH_HASH_KEYS.map((k) => [
              k,
              k === 'AUTH_MINWOO_PASSWORD_HASH' ? MINWOO_HASH : SEED_HASH,
            ]),
          ),
        ),
        generateStringKey: '_unused',
      },
    });

    // --- External API keys (CMS, Korea Eximbank). Static template so the value
    // is set once at create and never clobbered; actual keys are set out-of-band
    // (put-secret-value), not committed. ---
    const apiSecret = new secretsmanager.Secret(this, 'ApiSecret', {
      secretName: `${n('sm')}-api`,
      description: `esm ${envName} external API keys (value managed out-of-band)`,
      generateSecretString: {
        secretStringTemplate: JSON.stringify({ CMS_API_KEY: '', KOREAEXIM_API_KEY: '' }),
        generateStringKey: '_unused',
      },
    });

    // --- ECS cluster + ALB. ---
    const cluster = new ecs.Cluster(this, 'Cluster', {
      vpc,
      clusterName: n('ecs-cls'),
      containerInsightsV2: ecs.ContainerInsights.ENABLED,
      enableFargateCapacityProviders: true, // FARGATE_SPOT for the worker
    });

    // ALB reachable only from the office network (not the public internet).
    const OFFICE_CIDR = '211.111.0.0/16';
    const albSg = new ec2.SecurityGroup(this, 'AlbSg', {
      vpc,
      securityGroupName: `${n('sg')}-alb`,
      description: `ALB ingress from office network (${OFFICE_CIDR}) only`,
    });
    albSg.addIngressRule(ec2.Peer.ipv4(OFFICE_CIDR), ec2.Port.tcp(80), 'office http');
    albSg.addIngressRule(ec2.Peer.ipv4(OFFICE_CIDR), ec2.Port.tcp(443), 'office https');
    const alb = new elbv2.ApplicationLoadBalancer(this, 'Alb', {
      vpc,
      loadBalancerName: n('alb'),
      internetFacing: true,
      vpcSubnets: { subnetGroupName: 'pub-web' },
      securityGroup: albSg,
    });

    const frontendOrigin = [
      `http://${alb.loadBalancerDnsName}`,
      ...(props.hostname ? [`https://${props.hostname}`] : []),
      ...(props.extraOrigins ?? []),
    ].join(',');

    // --- Task: 2 containers, frontend proxies to backend over localhost. ---
    const logGroup = new logs.LogGroup(this, 'Logs', {
      logGroupName: `/ecs/sk-${envName}-an2-esm`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const taskDef = new ecs.FargateTaskDefinition(this, 'Task', {
      family: n('ecs-td'),
      cpu: 1024,
      memoryLimitMiB: 2048,
    });
    bucket.grantReadWrite(taskDef.taskRole);

    // Images are managed by the app pipeline (build -> push :latest -> force
    // redeploy). CDK only references the ECR repos; it never builds images.
    const backendRepo = ecr.Repository.fromRepositoryName(
      this, 'BackendRepo', `sk-${envName}-an2-ecr-esm-backend`);
    const frontendRepo = ecr.Repository.fromRepositoryName(
      this, 'FrontendRepo', `sk-${envName}-an2-ecr-esm-frontend`);

    // Shared by the backend (web) and the Celery worker containers.
    const backendEnv = {
      APP_ENV: isProd ? 'production' : 'development',
      // config.py assembles DATABASE_URL from these PG* parts.
      PGHOST: db.dbInstanceEndpointAddress,
      PGPORT: db.dbInstanceEndpointPort,
      PGUSER: 'esm',
      PGDATABASE: `esm_${envName}`,
      SCM_STORAGE_DIR: '/data',
      OBJECT_STORAGE_BUCKET: bucket.bucketName,
      OBJECT_STORAGE_REGION: this.region,
      FRONTEND_ORIGIN: frontendOrigin,
      // Sets CELERY_BROKER_URL too (config.py default), so analyses run on the
      // worker service below — keep both deployed together.
      REDIS_URL: redisUrl,
      // Frontend proxies to the backend over localhost, so without a trusted
      // proxy the backend sees one IP (127.0.0.1) and the per-IP login limit
      // acts globally. The ALB is already office-IP restricted, so relax it.
      SCM_LOGIN_RATE_LIMIT_MAX_ATTEMPTS: '1000',
    };
    const backendSecrets = () => ({
      PGPASSWORD: ecs.Secret.fromSecretsManager(db.secret!, 'password'),
      ...Object.fromEntries(
        AUTH_HASH_KEYS.map((k) => [k, ecs.Secret.fromSecretsManager(appSecret, k)]),
      ),
      CMS_API_KEY: ecs.Secret.fromSecretsManager(apiSecret, 'CMS_API_KEY'),
      KOREAEXIM_API_KEY: ecs.Secret.fromSecretsManager(apiSecret, 'KOREAEXIM_API_KEY'),
    });

    const backend = taskDef.addContainer('backend', {
      containerName: 'backend',
      image: ecs.ContainerImage.fromEcrRepository(backendRepo, 'latest'),
      essential: true,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'backend', logGroup }),
      environment: backendEnv,
      secrets: backendSecrets(),
      portMappings: [{ containerPort: 8002 }],
      healthCheck: {
        command: [
          'CMD-SHELL',
          "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8002/api/health/live').status==200 else 1)\"",
        ],
        interval: Duration.seconds(15),
        timeout: Duration.seconds(5),
        retries: 5,
        startPeriod: Duration.seconds(60),
      },
    });

    const frontend = taskDef.addContainer('frontend', {
      containerName: 'frontend',
      image: ecs.ContainerImage.fromEcrRepository(frontendRepo, 'latest'),
      essential: true,
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'frontend', logGroup }),
      environment: {
        NODE_ENV: 'production',
        FASTAPI_INTERNAL_BASE_URL: 'http://127.0.0.1:8002',
      },
      portMappings: [{ containerPort: 3000 }],
    });
    frontend.addContainerDependencies({
      container: backend,
      condition: ecs.ContainerDependencyCondition.HEALTHY,
    });

    // --- Fargate service in private subnets. ---
    const serviceSg = new ec2.SecurityGroup(this, 'ServiceSg', {
      vpc,
      securityGroupName: `${n('sg')}-svc`,
    });
    const service = new ecs.FargateService(this, 'Service', {
      cluster,
      serviceName: n('ecs-svc'),
      taskDefinition: taskDef,
      desiredCount: 1,
      securityGroups: [serviceSg],
      // Private app tier with NAT egress so Fargate can pull images from ECR.
      vpcSubnets: { subnetGroupName: 'priv-app' },
      assignPublicIp: false,
      minHealthyPercent: 0,
      maxHealthyPercent: 200,
      circuitBreaker: { rollback: true },
    });
    dbSg.addIngressRule(serviceSg, ec2.Port.tcp(5432), 'app to postgres');
    redisSg.addIngressRule(serviceSg, ec2.Port.tcp(6379), 'app to redis');

    // --- Celery worker: same backend image (command override), Fargate Spot.
    // acks_late + reject_on_worker_lost in celery_app.py make Spot interruptions
    // safe: unacked jobs are redelivered after the broker visibility timeout. ---
    const workerTaskDef = new ecs.FargateTaskDefinition(this, 'WorkerTask', {
      family: n('ecs-td-worker'),
      cpu: isProd ? 1024 : 512,
      memoryLimitMiB: isProd ? 2048 : 1024,
    });
    bucket.grantReadWrite(workerTaskDef.taskRole);
    workerTaskDef.addContainer('worker', {
      containerName: 'worker',
      image: ecs.ContainerImage.fromEcrRepository(backendRepo, 'latest'),
      command: [
        'celery', '-A', 'backend.worker.celery_app', 'worker',
        '--loglevel=info', '--concurrency=1',
      ],
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: 'worker', logGroup }),
      environment: backendEnv,
      secrets: backendSecrets(),
    });
    new ecs.FargateService(this, 'Worker', {
      cluster,
      serviceName: n('ecs-svc-worker'),
      taskDefinition: workerTaskDef,
      // Production uses two separate one-process workers. This gives two real
      // parallel analysis slots without forcing two memory-heavy analyses into
      // the same 2 GiB container. Development keeps one worker to limit cost.
      desiredCount: isProd ? 2 : 1,
      securityGroups: [serviceSg],
      vpcSubnets: { subnetGroupName: 'priv-app' },
      assignPublicIp: false,
      minHealthyPercent: 0,
      capacityProviderStrategies: [{ capacityProvider: 'FARGATE_SPOT', weight: 1 }],
    });

    // ALB -> frontend:3000 (CDK opens the service SG for the ALB automatically).
    // No explicit targetGroupName: a fixed name collides when the target group
    // moves between the HTTP and HTTPS listeners (create-new-before-delete-old).
    const targetProps: elbv2.AddApplicationTargetsProps = {
      port: 3000,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [service.loadBalancerTarget({ containerName: 'frontend', containerPort: 3000 })],
      healthCheck: {
        path: '/login',
        healthyHttpCodes: '200-399',
        interval: Duration.seconds(30),
      },
      deregistrationDelay: Duration.seconds(10),
    };
    // open:false — ingress is controlled by albSg (office CIDR only), not 0.0.0.0/0.
    const httpListener = alb.addListener('Http', { port: 80, open: false });
    if (props.certArn) {
      // HTTPS terminates at the ALB; HTTP redirects to it (permanent 301).
      alb
        .addListener('Https', {
          port: 443,
          open: false,
          certificates: [elbv2.ListenerCertificate.fromArn(props.certArn)],
        })
        .addTargets('Frontend', targetProps);
      httpListener.addAction('Redirect', {
        action: elbv2.ListenerAction.redirect({ protocol: 'HTTPS', port: '443', permanent: true }),
      });
    } else {
      httpListener.addTargets('Frontend', targetProps);
    }

    new CfnOutput(this, 'AlbUrl', { value: `http://${alb.loadBalancerDnsName}` });
    new CfnOutput(this, 'OutputBucket', { value: bucket.bucketName });
    new CfnOutput(this, 'AppSecretArn', { value: appSecret.secretArn });
    new CfnOutput(this, 'DbEndpoint', { value: db.dbInstanceEndpointAddress });
  }
}
