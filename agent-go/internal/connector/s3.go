package connector

import (
	"context"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

// s3Connector indexes an S3-compatible bucket.
// Works with: AWS S3, MinIO, Wasabi, Backblaze B2, Cloudflare R2.
type s3Connector struct {
	client   *s3.Client
	bucket   string
	prefix   string
	endpoint string   // empty = AWS, set for S3-compatible stores
}

func newS3(settings map[string]string) (Connector, error) {
	bucket := settings["bucket"]
	if bucket == "" {
		return nil, fmt.Errorf("s3 connector: 'bucket' is required")
	}

	var opts []func(*config.LoadOptions) error

	// Region
	if region := settings["region"]; region != "" {
		opts = append(opts, config.WithRegion(region))
	}

	// Static credentials (prefer IRSA/instance profile over static keys)
	if ak, sk := settings["access_key"], settings["secret_key"]; ak != "" && sk != "" {
		opts = append(opts, config.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(ak, sk, settings["session_token"]),
		))
	}

	cfg, err := config.LoadDefaultConfig(context.Background(), opts...)
	if err != nil {
		return nil, fmt.Errorf("s3: load config: %w", err)
	}

	var s3Opts []func(*s3.Options)
	if endpoint := settings["endpoint"]; endpoint != "" {
		s3Opts = append(s3Opts, func(o *s3.Options) {
			o.BaseEndpoint = aws.String(endpoint)
			o.UsePathStyle  = true // required for MinIO
		})
	}

	return &s3Connector{
		client:   s3.NewFromConfig(cfg, s3Opts...),
		bucket:   bucket,
		prefix:   strings.TrimPrefix(settings["prefix"], "/"),
		endpoint: settings["endpoint"],
	}, nil
}

func (c *s3Connector) Type() string { return "s3" }

func (c *s3Connector) Test(ctx context.Context) error {
	_, err := c.client.HeadBucket(ctx, &s3.HeadBucketInput{Bucket: &c.bucket})
	if err != nil {
		return fmt.Errorf("s3: cannot access bucket %q: %w", c.bucket, err)
	}
	return nil
}

func (c *s3Connector) Walk(ctx context.Context, fn WalkFunc) error {
	paginator := s3.NewListObjectsV2Paginator(c.client, &s3.ListObjectsV2Input{
		Bucket: &c.bucket,
		Prefix: aws.String(c.prefix),
	})

	for paginator.HasMorePages() {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}

		page, err := paginator.NextPage(ctx)
		if err != nil {
			return fmt.Errorf("s3: list page: %w", err)
		}

		for _, obj := range page.Contents {
			if obj.Key == nil {
				continue
			}
			key := *obj.Key
			if strings.HasSuffix(key, "/") {
				continue // skip directory markers
			}

			name := key
			if idx := strings.LastIndex(key, "/"); idx >= 0 {
				name = key[idx+1:]
			}

			var modTime time.Time
			if obj.LastModified != nil {
				modTime = *obj.LastModified
			}

			fileInfo := FileInfo{
				Path:       "/" + key,
				Name:       name,
				Extension:  strings.ToLower(ext(name)),
				Size:       aws.ToInt64(obj.Size),
				ModifiedAt: modTime.UTC(),
				IndexedAt:  time.Now().UTC(),
				Protocol:   "s3",
				Host:       c.bucket,
			}

			// ETag is MD5 of the object (or multipart hash) — use as xxhash proxy
			if obj.ETag != nil {
				fileInfo.XXHash = strings.Trim(*obj.ETag, `"`)
			}

			if err := fn(ctx, fileInfo); err != nil {
				return err
			}
		}
	}
	return nil
}

func (c *s3Connector) Open(ctx context.Context, path string) (io.ReadCloser, error) {
	key := strings.TrimPrefix(path, "/")
	result, err := c.client.GetObject(ctx, &s3.GetObjectInput{
		Bucket: &c.bucket,
		Key:    aws.String(key),
	})
	if err != nil {
		return nil, fmt.Errorf("s3: get object %q: %w", key, err)
	}
	return result.Body, nil
}

func init() {
	Register("s3",   newS3)
	Register("minio", newS3) // MinIO is S3-compatible
}
