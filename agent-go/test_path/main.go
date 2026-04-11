package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
)

func main() {
	paths := []string{
		"C:/Users/User/.openclaw/workspace",
		`C:\Users\User\.openclaw\workspace`,
	}
	for _, p := range paths {
		info, err := os.Stat(p)
		fmt.Printf("\nPath: %q\n  exists: %v  err: %v\n", p, err == nil, err)
		if err == nil && info.IsDir() {
			count := 0
			filepath.WalkDir(p, func(path string, d fs.DirEntry, werr error) error {
				if !d.IsDir() {
					count++
					if count <= 5 {
						fmt.Println("  FILE:", path)
					}
				}
				return nil
			})
			fmt.Printf("  total files: %d\n", count)
		}
	}
}
