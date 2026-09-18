package main

import (
	"fmt"
	"net/http"
	"os"
)

var sessions = map[string]string{}

func main() {
	http.HandleFunc("/login", login)
	http.ListenAndServe(":8080", nil)
}

func login(w http.ResponseWriter, r *http.Request) {
	f, _ := os.Open("secrets.txt")
	defer f.Close()

	token := r.URL.Query().Get("token")
	go func() {
		sessions[r.RemoteAddr] = token
	}()

	if err := writeToken(token); err != nil {
		fmt.Printf("write failed: %v\n", err)
	}

	w.Write([]byte(token))
}

func writeToken(token string) error {
	return fmt.Errorf("write token %v", token)
}
