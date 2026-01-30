package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/redis/go-redis/v9"
)

var (
	redisClient *redis.Client
	ctx         = context.Background()
)

type Response struct {
	Service string `json:"service"`
	Status  string `json:"status"`
	Message string `json:"message,omitempty"`
}

type HealthResponse struct {
	Status string `json:"status"`
	Redis  string `json:"redis"`
}

type CounterResponse struct {
	Counter int64  `json:"counter,omitempty"`
	Error   string `json:"error,omitempty"`
}

func main() {
	redisHost := os.Getenv("REDIS_HOST")
	if redisHost == "" {
		redisHost = "redis"
	}
	redisPort := os.Getenv("REDIS_PORT")
	if redisPort == "" {
		redisPort = "6379"
	}

	redisAddr := fmt.Sprintf("%s:%s", redisHost, redisPort)
	log.Printf("Connecting to Redis at %s", redisAddr)

	redisClient = redis.NewClient(&redis.Options{
		Addr:        redisAddr,
		DialTimeout: 5 * time.Second,
	})

	http.HandleFunc("/", homeHandler)
	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/counter", counterHandler)

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("Starting Go API server on port %s", port)
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatal(err)
	}
}

func homeHandler(w http.ResponseWriter, r *http.Request) {
	response := Response{
		Service: "Go API",
		Status:  "running",
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	_, err := redisClient.Ping(ctx).Result()
	if err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(HealthResponse{
			Status: "unhealthy",
			Redis:  "disconnected: " + err.Error(),
		})
		return
	}

	json.NewEncoder(w).Encode(HealthResponse{
		Status: "healthy",
		Redis:  "connected",
	})
}

func counterHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	count, err := redisClient.Incr(ctx, "go_visit_counter").Result()
	if err != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		json.NewEncoder(w).Encode(CounterResponse{
			Error: err.Error(),
		})
		return
	}

	json.NewEncoder(w).Encode(CounterResponse{
		Counter: count,
	})
}
